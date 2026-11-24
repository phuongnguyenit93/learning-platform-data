# Kafka and Database Commit Order

## 1. Why does commit order matter?

A business operation often both modifies data in a database and sends an event to Kafka. For example, when a customer places an order, the application needs to save the order in the database and emit `OrderCreated` so payment, inventory, or notification services can continue processing.

The two systems have two independent commit mechanisms:

- The database commits a JDBC/JPA transaction.
- Kafka commits a producer transaction to publish records; in consumer transactions, Kafka can also commit offsets alongside emitted output records.

Unless both commits belong to a true distributed transaction, there is always a window in which one system has committed while the other has not. Commit order determines which intermediate state can arise if the application or one of the systems fails between the two steps.

With Spring Kafka, transaction synchronization coordinates commit ordering between the database transaction manager and Kafka. This mechanism is useful, yet by itself it does not turn two resource managers into a single global atomic transaction. To understand actual behavior, examine commit order and failure windows.

## 2. Two fundamental commit orders

When a service both updates a database and sends records with `KafkaTemplate`, there are two main options:

1. **Database commits first, Kafka commits second (DB-first).** The database transaction is primary; the Kafka transaction is synchronized and commits after the database commit succeeds.
2. **Kafka commits first, database commits second (Kafka-first).** The database transaction is outer; a nested Kafka transaction inside commits before the outer method completes.

```text
DB-first
  Begin DB transaction
       |
       +-- update database
       +-- send Kafka record (Kafka transaction is synchronized)
       |
  Commit database
       |
  Commit Kafka transaction
       |
  Return

Kafka-first
  Begin DB transaction
       |
       +-- update database
       +-- Begin Kafka transaction (nested method)
       |       |
       |       +-- send Kafka record
       |       +-- Commit Kafka transaction
       |
  Commit database
       |
  Return
```

Neither option eliminates every possible skew between the database and Kafka. DB-first prioritizes avoiding publishing an event when the database has not committed; Kafka-first prioritizes committing the database only after Kafka has accepted the event. The choice depends on which business consequence the system prefers to guard against.

## 3. DB-first: database commits before Kafka

This is the default order when using the database transaction manager as the primary transaction and letting `KafkaTemplate` participate in transaction synchronization.

Service example:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("transactionManager")
    public void createOrder(Order order) {
        orderRepository.save(order);

        OrderCreated event = new OrderCreated(
                order.getId(), order.getCustomerId(), order.getTotal());

        kafkaTemplate.send("orders", order.getId(), event);
    }
}
```

In the example, `transactionManager` is the database transaction manager (such as `JpaTransactionManager` or `DataSourceTransactionManager`). The Kafka producer factory must support transactions and `KafkaTemplate` must use that same transaction-capable `ProducerFactory`.

With Spring Boot, you can enable Kafka producer transactions via:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-service-${INSTANCE_ID:local}-
```

When `transaction-id-prefix` is present, Spring Boot configures a transaction-capable producer factory and the corresponding `KafkaTransactionManager`. Each application instance needs a unique prefix to avoid producers fencing one another. If configuring the producer factory manually, set a unique transaction ID prefix and pass that exact factory to `KafkaTemplate`.

In a DB-first transaction, when the method finishes normally, Spring commits the database first. The synchronized Kafka transaction commits afterward. If the database rolls back, the synchronized Kafka transaction rolls back as well.

### Failure window of DB-first

Suppose the database commit succeeds yet the Kafka commit fails:

```text
Database: COMMITTED
Kafka:    COMMIT FAILED
```

As a result, the order exists in the database while `OrderCreated` has not been published. Downstream services do not know a new order was created. This is the state of **database has data, yet the event is missing**.

Since Spring Kafka 2.5.17, 2.6.12, 2.7.9, and 2.8.0, commit failures of a synchronized transaction after the primary transaction has committed are thrown to the caller. In earlier versions, this failure was only logged at debug level. Even though an exception is thrown, the database has already committed, so automatic DB rollback cannot be expected; the application needs compensation or reconciliation.

DB-first fits when you prioritize not emitting events for unconfirmed database changes. Still, you must address the case where DB committed and Kafka did not.

## 4. Kafka-first: Kafka commits before the database

If you want Kafka to commit first, Spring Kafka prescribes two nested `@Transactional` methods: the outer method uses the database transaction manager, and the inner method uses `KafkaTransactionManager`.

Declare the Kafka transaction manager using the same producer factory as the template:

```java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

The outer method holds the DB transaction:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional("transactionManager")
    public void createOrder(Order order) {
        orderRepository.save(order);
        eventPublisher.publish(new OrderCreated(
                order.getId(), order.getCustomerId(), order.getTotal()));
    }
}
```

The inner method opens and commits the Kafka transaction:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderEvent event) {
        kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

The two services are separated so that `eventPublisher.publish()` goes through the Spring proxy and transaction interceptor. Calling another `@Transactional` method in the same object via `this.publish()` bypasses the default proxy, so the Kafka transaction may not open as expected.

When `publish()` finishes, the Kafka transaction commits. Only after this call returns does the outer method complete and commit the DB transaction. This is the Kafka-first order.

### Failure window of Kafka-first

If Kafka commits successfully yet the database commit fails:

```text
Kafka:    COMMITTED
Database: COMMIT FAILED / ROLLED BACK
```

The `OrderCreated` event has appeared to consumers, yet the order does not exist or was not saved in the database. Consumers may execute side effects based on an event that the primary data source never confirmed.

Kafka-first may fit when event publication is a prerequisite before finalizing the DB, though it is risky if downstream treats events as final truth. Consumers must tolerate events arriving ahead of DB state or have compensation mechanisms.

## 5. Comparing the failure windows

| Scenario | DB-first | Kafka-first |
|---|---|---|
| DB commit fails | Kafka transaction rolls back; no event published | Kafka may have committed earlier; event may exist despite DB rollback |
| Kafka commit fails | DB already committed; event missing | Kafka has not committed; outer DB transaction can roll back if error propagates before DB commit |
| Process stops between commits | DB may have committed while Kafka has not | Kafka may have committed while DB has not |
| Downstream reads event | Only after Kafka commits; DB committed first | May read event before DB commits |
| Compensation action | Replay event based on DB data | Cancel/compensate event or fix downstream state |

This table assumes errors propagate across transaction boundaries and transaction managers are properly configured. Lost connections, timeouts, or uncertain commit results can leave the caller unsure whether the broker or database committed. Reconcile using business identifiers rather than inferring purely from client-side exceptions.

## 6. Transaction synchronization is not distributed atomic commit

Spring transaction synchronization coordinates commit/rollback callbacks across transaction managers, yet does not provide a transaction coordinator capable of atomically committing or rolling back both a database and Kafka as an XA global transaction.

This means:

- Both resources still have separate transactions and separate commits.
- Spring chooses the commit order and reports errors when one step fails.
- Once the first resource has committed and the second fails, the first resource cannot be rolled back via an ordinary rollback command.
- An exception returned to the caller does not mean all resources rolled back.
- Idempotency, reconciliation, compensation, or outbox/inbox are required to handle gaps.

Hence this is commonly called **Best Efforts 1PC**: the system tries to coordinate two local transactions in a chosen order, without achieving global atomic commit. Never describe this mechanism as "DB and Kafka commit strictly atomically."

## 7. Configuring the transaction manager and `ProducerFactory`

For Kafka transactions to participate in Spring transactions:

1. `DefaultKafkaProducerFactory` must be configured with `transactionIdPrefix`.
2. `KafkaTemplate` must use a transaction-capable producer factory.
3. `KafkaTransactionManager` must use that exact producer factory.
4. When synchronizing with a DB transaction manager, do not create separate producer factories for the template and the transaction manager.
5. With multiple instances, each instance must have a distinct `transactionIdPrefix`.

Basic producer configuration example:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-${INSTANCE_ID:local}-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

If using Spring Boot auto-configuration, verify the auto-configured `KafkaTemplate`, producer factory, and transaction manager beans. If declaring beans manually, ensure they share the same producer factory. Never declare a `KafkaTransactionManager` with a different factory than the template sending records.

When the producer factory is transactional, sends via the template must occur inside a transaction opened by `@Transactional`, `TransactionTemplate`, a listener container, or `executeInTransaction()`. Calling the template outside a transaction can throw `IllegalStateException`, unless `allowNonTransactional` is configured to permit non-transactional sends.

## 8. Commit order when a consumer receives a record and updates the database

Another common flow is a consumer reading an event, updating a database, and committing the Kafka offset. When you want to coordinate DB results and offsets in one flow, you can have the listener container open a Kafka transaction and the listener method open a DB transaction.

With a container-initiated Kafka transaction:

1. The container starts a Kafka transaction.
2. The listener receives a record and calls a service annotated with `@Transactional` using the DB transaction manager.
3. The DB transaction commits when the listener method finishes successfully.
4. The container commits the Kafka transaction; the offset is sent inside this transaction.

Listener example:

```java
@Component
public class PaymentListener {

    private final PaymentApplicationService paymentService;

    public PaymentListener(PaymentApplicationService paymentService) {
        this.paymentService = paymentService;
    }

    @KafkaListener(topics = "orders", groupId = "payment-service")
    public void onOrder(OrderCreated event) {
        paymentService.createPayment(event);
    }
}
```

Service updating the DB:

```java
@Service
public class PaymentApplicationService {

    private final PaymentRepository paymentRepository;

    public PaymentApplicationService(PaymentRepository paymentRepository) {
        this.paymentRepository = paymentRepository;
    }

    @Transactional("transactionManager")
    public void createPayment(OrderCreated event) {
        paymentRepository.save(Payment.pendingFor(event.orderId()));
    }
}
```

The container must be configured to use `KafkaTransactionManager`; with Spring Boot and `spring.kafka.producer.transaction-id-prefix`, Boot can auto-configure the transaction manager and wire it into the listener container. If configuring the factory manually, set the Kafka-aware transaction manager on `ContainerProperties` using the API for your Spring Kafka version.

In this model, the DB commits before the Kafka transaction/offset commit. If the DB commit fails, the exception rolls back the Kafka transaction and the offset is not committed, allowing redelivery. If the DB commit succeeds yet the Kafka transaction commit fails, the record may be redelivered even though the DB already contains the payment. Thus `createPayment()` must be idempotent, such as via a unique constraint on `orderId` or event ID.

Do not use non-blocking retry topics together with container transactions. Spring Kafka does not support combining non-blocking retries with container transactions in this way; when the listener throws an exception, the container transaction may commit and route the record to the retry topic. Pick a retry strategy compatible with your transaction model.

## 9. Why you should not rely on `ChainedKafkaTransactionManager`

`ChainedKafkaTransactionManager` has been deprecated since Spring Kafka 2.7. It builds on `ChainedTransactionManager` to invoke multiple transaction managers sequentially, yet does not turn them into a single atomic global transaction.

When one transaction manager commits and the next fails, the system still ends up with a partial commit. Therefore, do not use `ChainedKafkaTransactionManager` as a guarantee that DB and Kafka always commit or roll back together.

For new applications:

- Producer-only flow: use transaction synchronization with the primary transaction manager and intentionally select DB-first or nested Kafka-first ordering.
- Consumer-initiated flow: have the container use `KafkaTransactionManager`, and have the listener method use the database transaction manager.
- If high reliability between DB and Kafka is required: prefer transactional outbox/inbox with idempotency.

When maintaining legacy applications using `ChainedKafkaTransactionManager`, inspect manager ordering, failure windows, and partial commit handling before upgrading. Do not swap it out mechanically without accounting for listener container offset and retry semantics.

## 10. Transactional outbox: a common solution for DB and Kafka

If the business requirement is "once the database saves the change, the event is guaranteed to be published," transactional outbox is usually a better design than choosing DB-first or Kafka-first.

Within a single database transaction, the application:

1. Updates the business table, such as `orders`.
2. Inserts a row into `outbox_events` containing event ID, aggregate ID, event type, payload, and creation timestamp.
3. Commits the database transaction.

A relay process or CDC connector reads the outbox and publishes events to Kafka. Upon successful send, the relay marks the row as published or relies on CDC log offsets to continue.

```text
Application command
       |
       v
Begin DB transaction
       |
       +---- UPDATE orders
       |
       +---- INSERT outbox_events
       |
       v
Commit DB transaction
       |
       v
Outbox relay / CDC connector
       |
       v
Publish to Kafka
       |
       v
Consumer services
```

If the DB transaction rolls back, neither the business change nor the outbox row exists. If the DB commits and the relay pauses temporarily, the outbox row remains for the relay to emit after recovery. This eliminates the "DB committed without persistent info to emit" failure window inside the application transaction.

An outbox relay can still publish duplicates if Kafka send succeeds and the process stops before marking the outbox row as sent. Thus outbox typically provides **at-least-once publication**; consumers must be idempotent by `eventId`. If per-aggregate ordering is needed, the relay must partition/read outbox rows by aggregate key and preserve emission order.

### Example outbox table

```sql
CREATE TABLE outbox_events (
    event_id       VARCHAR(100) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(150) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
```

Writing business data and outbox in the same transaction:

```java
@Transactional("transactionManager")
public void createOrder(Order order) {
    orderRepository.save(order);

    OrderCreated event = OrderCreated.from(order);
    String payload;
    try {
        payload = objectMapper.writeValueAsString(event);
    } catch (JsonProcessingException exception) {
        throw new IllegalStateException("Cannot serialize outbox event", exception);
    }

    outboxRepository.save(OutboxEvent.pending(
            event.eventId(),
            "Order",
            order.getId(),
            "OrderCreated",
            payload));
}
```

The relay can be implemented as a polling worker with row locking/claiming or via CDC such as Debezium Outbox Event Router. Manage retries, leases/claims, cleanup, retention, and replayability. Never let two relays publish the same row without claiming or deduplication.

## 11. Inbox and consumer-side idempotency

Outbox lowers the risk of losing events on the producer side, yet the relay can still send duplicates. Consumers should guarantee idempotent processing using `eventId`.

A common pattern is an inbox table:

```sql
CREATE TABLE processed_events (
    event_id     VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Within the same DB transaction as the business side effect:

```java
@Transactional("transactionManager")
public void handle(OrderCreated event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    paymentRepository.createPendingPayment(event.orderId());
}
```

`insertIfAbsent` must be implemented using a unique constraint and a database-appropriate atomic statement (such as `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL). Do not use an unlocked "SELECT then INSERT" pattern, because two concurrent consumers can both see the event as absent.

If the DB transaction commits while the Kafka offset has not committed, the record will be redelivered. The inbox detects the already-processed event and avoids repeating side effects. The listener then finishes so the container commits the offset.

An inbox does not protect external side effects outside the database unless they participate in the same transaction or carry their own idempotency key. For example, calling a payment gateway, sending email, or making HTTP calls requires downstream-supported idempotency keys or an outbox for the outbound call.

## 12. Does exactly-once solve DB and Kafka commits?

Kafka exactly-once semantics (EOS) can protect consume-transform-produce flows within Kafka when output records and consumed offsets commit in the same Kafka transaction. Consumers use `isolation.level=read_committed` to read only committed records.

Kafka EOS does not automatically extend to database transactions. When a listener both writes to a DB and commits a Kafka offset, DB and Kafka remain two independent resources. If DB commit succeeds and Kafka commit fails, the record can be redelivered and DB side effects can repeat.

Therefore:

- Kafka transactions protect atomicity across Kafka records sent and Kafka offsets enlisted in the transaction.
- Database transactions protect changes inside the database.
- Transaction synchronization selects ordering and coordinates commit callbacks.
- Outbox/inbox/idempotency resolve practical gaps between the two resources.

Do not call a DB + Kafka workflow exactly-once merely because it uses `@Transactional` and `KafkaTransactionManager`. Describe the exact guarantee boundaries and duplicate handling accurately.

## 13. Choosing commit order by business requirement

| Priority requirement | Suitable direction | What must be handled |
|---|---|---|
| Do not emit event if DB has not committed | DB-first or transactional outbox | DB committed while Kafka has not; outbox is usually more durable |
| Kafka must receive event before DB finalizes | Kafka-first | Consumers may observe the event even if DB rolls back |
| Consumer updates DB then commits offset | Container Kafka transaction + DB transaction in listener | DB commits before Kafka offset; needs inbox/idempotency on redelivery |
| Zero tolerance for losing events after DB commit | Transactional outbox | Relay retries and consumer deduplication |
| Coordinating multiple services across steps | Saga/compensation combined with outbox | State design, timeouts, and compensating actions |

In most business systems, transactional outbox combined with consumer idempotency is easier to operate and recover than trying to pick a commit order that hides every failure window.

## 14. Saga and compensation when two systems diverge

When a database and Kafka cannot commit atomically, one approach is accepting separate business steps and defining compensating actions.

Example order placement flow:

1. Order service saves the order in `PENDING` state and an `OrderCreated` outbox event.
2. Payment service receives the event and creates an idempotent payment intent.
3. If payment succeeds, Payment service emits `PaymentAuthorized`.
4. If payment fails, Payment service emits `PaymentRejected`.
5. Order service transitions the order to `CONFIRMED` or `CANCELLED` based on the event.

Each step updates its database and outbox in a local transaction. A saga does not roll back committed transactions in other services; it issues compensating actions, such as canceling a reservation or refunding. Use event IDs, correlation IDs, timeouts, and saga state to handle duplicates and out-of-order events.

## 15. Testing commit order and failure windows

Do not test only the happy path. Proactively inject failures between the two commits to verify the system can recover:

1. **DB-first success:** confirm DB row exists and event appears in Kafka after commit.
2. **DB rollback:** trigger an exception before DB commit; confirm the synchronized Kafka transaction does not publish the event.
3. **Kafka commit failure after DB commit:** simulate broker unavailability or commit error; confirm DB remains committed and the application records state requiring reconciliation.
4. **Kafka-first success:** confirm Kafka commit completes before DB commit.
5. **DB commit failure after Kafka commit:** simulate a constraint violation or DB outage; confirm the event may already exist and verify compensating action.
6. **Listener DB commit failure:** confirm the Kafka container transaction rolls back and the offset is not committed.
7. **Listener Kafka commit failure after DB commit:** confirm the record can redeliver and inbox/idempotency prevents duplicate side effects.
8. **Outbox relay stops after publish:** confirm the same event can be republished and consumers deduplicate by event ID.
9. **Multiple instances:** confirm transaction ID prefixes do not collide and no unexpected producer fencing occurs.
10. **Restart/rebalance:** confirm offsets, transaction recovery, and post-redelivery side effects follow policy.

In integration tests, use a real Kafka broker or Testcontainers Kafka alongside a test database. Assert both DB state and Kafka records, not merely that a method threw an exception. For indeterminate commit failures, verify final state using event ID or business key.

## 16. Observability and operations

Record:

- DB and Kafka commit outcomes, including exceptions from synchronized transactions.
- Kafka transaction aborts/commits, producer fencing, and transaction timeouts.
- Pending outbox row count, age of the oldest row, and relay publish rate.
- Duplicate publish counts or inbox duplicates skipped.
- Consumer lag, redeliveries, and listener rollback counts.
- Pending sagas, timeouts, and compensation failures.

Logs should include `eventId`, `aggregateId`, correlation ID, transaction flow, topic, partition, and offset where available. Do not log sensitive payloads or credentials. Metric tags should use only low-cardinality values such as topic, listener, and outcome; never use event ID or offset as tags.

## 17. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| DB committed yet event is missing | DB-first and subsequent Kafka commit failed | Reconcile by event ID; use outbox to persist emission intent durably |
| Consumer sees event yet DB row is missing | Kafka-first and subsequent DB commit failed | Design compensation or switch to DB-first/outbox |
| `KafkaTemplate` reports no transaction | `ProducerFactory` lacks `transactionIdPrefix` or send occurred outside transaction | Enable transactional producer and open an appropriate transaction |
| `KafkaTemplate` and `KafkaTransactionManager` are not in the same transaction | Two different `ProducerFactory` beans used | Share a single producer factory |
| Kafka producer fencing | Duplicate `transactional.id`/prefix across instances or old producer still active | Assign unique prefixes per instance and check producer lifecycle |
| Nested `@Transactional` does not start a Kafka transaction | Internal call within the same bean bypassing the proxy | Extract publisher into a separate bean or use `TransactionTemplate` |
| Redelivered record causes duplicate DB writes | DB committed while Kafka offset did not commit | Use inbox, unique constraints, and idempotent handlers |
| Assuming `ChainedKafkaTransactionManager` guarantees atomicity | Chained manager only orchestrates sequential local commits | Account for partial commits; use outbox/inbox or compensation |
| Using non-blocking retry with container transactions | The two mechanisms are incompatible in that combination | Choose blocking retry/`AfterRollbackProcessor` or retry topics without container transactions |

## 18. Design workflow

1. Determine whether the workflow is a producer emitting events after DB writes or a consumer updating DB after receiving events.
2. List undesired states if the process stops between commit steps.
3. If using transaction synchronization, choose DB-first or Kafka-first based on business impact and document the failure window.
4. Confirm the Kafka producer factory is transactional and shared by the template and transaction manager.
5. For consumer transactions, configure the container with `KafkaTransactionManager` and the listener with the DB transaction manager.
6. Use inbox/idempotency to handle redeliveries and duplicate side effects.
7. If DB commits must always yield corresponding events, implement transactional outbox.
8. If workflows span multiple services, define saga states and compensation.
9. Test failures at every point between DB commit and Kafka commit, including restarts and rebalances.
10. Monitor outbox backlog, commit failures, duplicates, and compensations in operations.

## 19. Summary

- DB-first commits the database first and Kafka second; a Kafka failure after DB commit can leave DB data without an event.
- Kafka-first commits Kafka first and the database second; a DB failure after Kafka commit can leave an event without corresponding source data.
- Spring Kafka transaction synchronization coordinates local transaction commit ordering, not distributed atomic commit.
- In consumer-initiated transactions, the listener container opens the Kafka transaction while the listener method may open a DB transaction; DB commits before Kafka transaction/offset commit, requiring idempotency on redelivery.
- `ChainedKafkaTransactionManager` is deprecated since Spring Kafka 2.7 and does not solve partial commits.
- Transactional outbox writes business changes and events in the same DB transaction, then a relay/CDC publishes to Kafka.
- Outbox can publish duplicates; consumer inbox/idempotency handles duplicates via event ID and unique constraints.
- Kafka EOS protects Kafka records and offsets inside Kafka transactions; it does not extend exactly-once to databases or HTTP.
- Choose commit order based on failure windows, and use outbox/inbox/compensation when business reliability requirements are high.

Commit order is a decision about which state can surface when the system fails. By understanding DB-first, Kafka-first, and transaction boundaries, teams can pick the right design, test failure windows, and build recovery mechanisms instead of assuming two systems always commit together.

## References

- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka Reference — Tips, Tricks and Examples](https://docs.spring.io/spring-kafka/reference/tips.html)
- [Spring Kafka API — KafkaTransactionManager](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/transaction/KafkaTransactionManager.html)
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Debezium Documentation — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
