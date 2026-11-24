# Synchronizing Kafka Transactions with DB Transactions

In a Spring Kafka application, a business flow often needs to **write to a database and publish a Kafka event** after processing a message. For example, a consumer receives an order creation command, updates the `orders` table in PostgreSQL, and then publishes `OrderAccepted` to Kafka so other services can continue processing. These two operations belong to **two systems with separate transaction managers**: the database commits a SQL transaction, while Kafka commits a Kafka transaction.

Spring supports **transaction synchronization** to coordinate the start, completion, and commit order of transactions. However, synchronizing commit order is **not** an atomic distributed transaction between the database and Kafka. If one side commits while the other fails, data can still diverge. This is the core problem to understand when designing Kafka and database reliability.

This lesson explains how Spring Kafka coordinates `KafkaTransactionManager` with a database transaction manager, common commit orders, failure windows, idempotency, transactional outbox, and how to test failure scenarios in production.

## 1. The dual-write problem

Consider a service that consumes an event from the `orders.requested` topic and performs two actions:

1. Write the order to the database.
2. Send an `OrderCreated` event to the `orders.created` topic.

~~~text
orders.requested
       |
       v
Spring Kafka listener
       |
       +----> PostgreSQL: INSERT orders
       |
       +----> Kafka: publish orders.created
~~~

If both steps succeed, the data is consistent. However, if a crash, timeout, or commit failure occurs between the two operations:

| DB state | Kafka event state | Consequence |
|---|---|---|
| Uncommitted | Uncommitted | Can be retried from the beginning |
| Committed | Committed | Desired state |
| Committed | Uncommitted | DB changed, but downstream has not received the event |
| Uncommitted | Committed | Downstream sees the event while DB has no record |

The last two rows represent **dual-write inconsistency**. Enabling separate transactions for each system does not solve this, because the two commits can succeed or fail independently.

Key distinctions to establish from the start:

- **Local DB transaction** guarantees atomicity for operations participating in the same database transaction.
- **Kafka transaction** guarantees that Kafka output records and, when configured as a consumer-initiated transaction, consumed offsets can commit or abort together within Kafka.
- **Spring transaction synchronization** coordinates callbacks/transaction boundaries, but does not turn two transaction managers into an atomic two-phase commit.
- **Transactional outbox** uses a single DB transaction to write business state together with the event record to be published, then publishes to Kafka in a separate step to eliminate the gap where an event is lost after a DB commit.

## 2. Transaction managers in Spring

A Spring Boot application using JPA and Kafka typically has:

| Component | Responsibility | Managed resource |
|---|---|---|
| **JpaTransactionManager** | Begin/commit/rollback DB transaction for JPA | JDBC connection and JPA EntityManager |
| **DataSourceTransactionManager** | Begin/commit/rollback DB transaction for JDBC | JDBC connection |
| **KafkaTransactionManager** | Begin/commit/abort Kafka transaction | Transactional KafkaProducer |
| **KafkaMessageListenerContainer** | Poll, invoke listener, coordinate offsets, and handle errors | KafkaConsumer and container lifecycle |
| **KafkaTemplate** | Publish Kafka records and participate in the appropriate transaction | KafkaProducer |

A typical application chooses **one database transaction manager suited to its persistence stack**, rather than using both `JpaTransactionManager` and `DataSourceTransactionManager` on the same operation and assuming they merge automatically.

The **@Transactional** annotation selects a transaction manager based on Spring configuration, bean name/qualifier, and transaction context. When multiple managers exist, specify it explicitly:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void updateDatabase(...) {
    // Runs inside a DB transaction.
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void publishEvents(...) {
    // Runs inside a Kafka transaction if the producer factory is transactional.
}
~~~

This is only an example of how to select a manager; the beans named `dbTransactionManager` and `kafkaTransactionManager` must be declared or confirmed to actually exist. **@Transactional** does not automatically open a distributed transaction covering every resource invoked inside the method.

## 3. What does a Kafka transaction guarantee?

A Kafka transaction is useful when you need to send multiple output records atomically or implement **Kafka consume → process → produce** with source offsets included in the same transaction.

~~~text
Kafka transaction T1:
    produce orders.created
    produce orders.audit
    send consumed offset if consume-process-produce
    COMMIT

Kafka result:
    outputs and offsets committed together
~~~

If T1 aborts, Kafka records from the aborted transaction will not be returned to **read_committed** consumers. When consumed offsets are part of the transaction, that offset commit is also not recorded.

A Kafka transaction **does not control PostgreSQL transactions**. The producer cannot automatically undo a committed DB UPDATE simply because the Kafka commit failed. Likewise, the database cannot delete a committed Kafka record with a SQL rollback.

Therefore, saying "both Kafka and DB are marked transactional" is not sufficient to conclude that the system provides end-to-end exactly-once semantics.

## 4. Two common ways to start transactions

There are two contexts to distinguish:

### Producer-initiated: the service method starts with a DB transaction

The service executes business logic inside a `@Transactional` method using the DB manager, then calls `KafkaTemplate`. If the producer factory is configured as transactional and `KafkaTemplate` participates in Spring transaction synchronization, the Kafka transaction is coordinated with the DB transaction.

~~~text
@Transactional DB service
       |
       +-- DB write
       +-- KafkaTemplate.send(...)
       |
       v
DB commit
       |
       v
Kafka transaction commit (synchronized)
~~~

In this flow, **the DB commits first and Kafka commits second** according to the common synchronization order. These are still two separate commits with a failure window between them.

### Consumer-initiated: the Kafka listener container starts a Kafka transaction

The container has a Kafka transaction manager and starts a Kafka transaction before invoking the listener. Inside the listener, a service method annotated with `@Transactional` using the DB manager opens a DB transaction.

~~~text
Kafka listener container: BEGIN Kafka transaction
       |
       v
@KafkaListener calls DB service
       |
       v
@Transactional DB service: BEGIN DB transaction
       |
       +-- DB write
       +-- KafkaTemplate.send(...) in the same Kafka transaction
       |
       v
DB transaction COMMIT
       |
       v
Listener completes
       |
       v
Container sendOffsetsToTransaction + COMMIT Kafka transaction
~~~

In this flow, because the DB transaction is nested **inside** the container transaction, the DB usually commits before Kafka. The Kafka commit can include both outputs and source consumed offsets.

The two models have different boundaries, yet both must handle the case where the DB has committed and the Kafka commit subsequently fails.

## 5. Configuring a transactional Kafka producer in Spring Boot

For `KafkaTemplate` to participate in a Kafka transaction, the producer factory must be configured as transactional. A common Spring Boot configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-instance-a-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[acks]": all
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Important points:

- **transaction-id-prefix** configures Spring Kafka to create transactional producers with a `transactional.id`.
- The prefix must be managed so that it **does not collide across concurrently active application instances**.
- **enable-auto-commit: false** prevents the consumer from committing offsets outside the container-managed transaction.
- **isolation-level: read_committed** ensures the consumer does not read aborted transactional records when the topic has transactional producers.
- **acks=all** supports producer durability, but does not replace Kafka transactions or proper broker replication settings.

When properly configured, Spring Boot can auto-configure a `KafkaTransactionManager`. If you declare multiple `ProducerFactory` or transaction manager beans manually, explicitly wire which beans are used by `KafkaTemplate` and the listener container.

The `transaction-id-prefix` example in YAML is only illustrative for a single instance. On Kubernetes, ensure stable instance identity while a pod is running and prevent `transactional.id` conflicts when scaling.

## 6. Example of a Kafka listener and DB transaction

Suppose we have an `OrderRequested` model, an `Order` entity, and an `OrderAccepted` output. A Kafka listener reads the input and invokes the service:

~~~java
@Component
public class OrderRequestListener {

    private final OrderApplicationService service;

    public OrderRequestListener(OrderApplicationService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "orders.requested",
            groupId = "orders-service",
            containerFactory = "transactionalListenerFactory")
    public void onOrder(OrderRequested event) {
        service.saveAndPublish(event);
    }
}
~~~

The service uses the **database transaction manager**:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderAccepted> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderAccepted> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void saveAndPublish(OrderRequested event) {
        Order order = Order.from(event);
        orderRepository.save(order);

        OrderAccepted accepted =
                new OrderAccepted(order.getId(), event.eventId());

        kafkaTemplate.send(
                "orders.accepted",
                order.getId(),
                accepted
        ).join();
    }
}
~~~

The snippet above illustrates transaction boundaries; the classes and beans in a real application must be declared accordingly. **KafkaTemplate must use a ProducerFactory that participates in the same Kafka transaction as the container.** Otherwise, the Kafka operation may commit outside the intended transaction.

Because the listener invokes the service through a separate Spring bean, the **@Transactional** proxy is applied. If a method is called via **this.saveAndPublish(...)** inside the same bean through self-invocation, Spring's proxy-based transaction interception may not run; that is a common mistake.

### Meaning of join()

`KafkaTemplate.send(...)` is normally asynchronous. Calling `join()` in the example helps surface produce errors early before the method returns. However, **a successful send does not mean the Kafka transaction has committed**. In a container-managed transaction model, the Kafka commit happens when the outer transaction boundary completes.

Therefore, the following can happen:

~~~text
DB service:
    UPDATE DB
    Kafka send acknowledged
    DB COMMIT succeeds

Kafka listener container:
    Kafka COMMIT fails
~~~

In this situation, the DB has already changed, while the Kafka output or consumed offset may not be committed according to the final transaction outcome. Calling `join()` does not eliminate that failure window.

## 7. Attaching a Kafka transaction manager to the listener container

For consumer-initiated transactions, the listener container must be configured with a transaction manager backed by the right transactional producer factory.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderRequested>
        transactionalListenerFactory(
                ConsumerFactory<String, OrderRequested> consumerFactory,
                KafkaTransactionManager<String, OrderAccepted> kafkaTxManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderRequested>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTxManager);
    return factory;
}
~~~

This example uses the **setKafkaAwareTransactionManager** API available in supported Spring Kafka versions; the setter name or wiring approach may differ in older versions. In a project using Spring Boot auto-configuration, this bean may not be needed if the container factory already receives the right manager.

`KafkaTransactionManager` uses the transactional `ProducerFactory`:

~~~java
@Bean
KafkaTransactionManager<String, OrderAccepted> kafkaTransactionManager(
        ProducerFactory<String, OrderAccepted> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Avoid creating two separate `KafkaTransactionManager` beans simply because one is auto-configured by Spring Boot and another is defined manually by the application, if doing so causes the template and container to use different transaction infrastructure.

## 8. DB-first commit: default order and benefits

In many applications using a DB `@Transactional` inside a transactional Kafka listener, the typical order is:

~~~text
T0  Consumer poll input
T1  Kafka container begin transaction K1
T2  DB service begin transaction D1
T3  UPDATE / INSERT in D1
T4  KafkaTemplate sends output in K1
T5  DB service return -> COMMIT D1
T6  Listener return
T7  Container sends source offset into K1
T8  Container COMMIT K1
~~~

Advantages of **DB-first, Kafka-second** order:

- If the DB transaction fails and the exception propagates out, the Kafka transaction can abort before outputs are made visible.
- Prevents publishing committed Kafka events when the DB write fails before commit.
- Easy to reason about when the DB is the source of truth for business state.

Critical drawback: **if D1 commits successfully but K1 fails to commit, the DB cannot roll back automatically**. A recovery mechanism is required so that Kafka eventually receives the corresponding event without re-executing business side effects incorrectly.

If a Kafka transaction commit returns an error due to network or coordinator issues, the final commit state sometimes needs investigation rather than assuming the transaction definitely aborted. Never trigger automatic DB compensation without evaluating the actual outcome.

## 9. The failure window after DB commit

This is the highest-impact failure window in the transaction synchronization model:

~~~text
DB transaction D1:
   INSERT order O-1001
   COMMIT D1 -> SUCCESS

Kafka transaction K1:
   SEND OrderAccepted(O-1001)
   COMMIT K1 -> FAILURE / UNKNOWN

Application:
   receives exception or restarts
~~~

At that point:

- The database already contains order `O-1001`.
- The Kafka transaction may have aborted or have a status that requires verification.
- The consumer group may not have the consumed offset committed from K1.
- The input record may be reprocessed.

If the retry simply re-runs `INSERT order` by primary key, it may hit a duplicate key error. If the code sees the order already exists and immediately returns, **the missing Kafka event may never be produced**.

Example of a logic bug:

~~~java
@Transactional("dbTransactionManager")
public void handle(OrderRequested event) {
    if (orderRepository.existsById(event.orderId())) {
        return;  // Dangerous: may skip an event that has not been published yet!
    }

    orderRepository.save(Order.from(event));
    kafkaTemplate.send("orders.accepted", ...).join();
}
~~~

The code above looks idempotent with respect to the DB, but **does not guarantee the Kafka output**. If the DB commits and the Kafka commit fails, the retry sees that the order exists and never resends the event.

This is why you must distinguish **DB operation idempotency** from **event publishing reliability**. Transactional outbox or a durable state machine tracking unpublished events is a better fit when events must not be lost.

## 10. Kafka commit exceptions after DB commit

When the DB transaction has committed and the subsequent Kafka transaction commit fails, the application needs to know about the failure to perform compensation or reconciliation.

Exception propagation behavior in Spring Kafka has evolved across version branches: in modern patch releases, failures in a secondary Kafka commit during transaction synchronization are typically **thrown to the caller**, rather than merely logged as in some older versions. Verify the behavior of the exact Spring Kafka version you are running.

It is important to distinguish:

- **Exception from `KafkaTemplate.send()`** before DB commit: can cause the DB to roll back if propagated.
- **Exception from DB commit**: the DB may roll back or its state may need verification depending on the error.
- **Exception from Kafka commit after DB commit**: the DB has already committed; you can no longer simply roll back that DB transaction.
- **Timeout while waiting for commit result**: you must investigate whether the broker already committed; never assume it always failed.

If recovery requires business compensation, the compensating action itself can fail and needs idempotency. For critical pipelines, design a **durable recovery record** upfront rather than relying on the process staying alive to catch the exception and resend to Kafka.

## 11. Kafka-first: can the commit order be reversed?

Spring allows nesting `@Transactional` methods so that a Kafka transaction commits before the DB transaction in certain producer-initiated workflows.

Example design with two Spring beans and two managers:

~~~java
@Service
public class DbWorkflowService {

    private final OrderRepository orderRepository;
    private final KafkaPublishingService publisher;

    @Transactional("dbTransactionManager")
    public void saveThenPublish(OrderRequested event) {
        orderRepository.save(Order.from(event));
        publisher.publishInKafkaTransaction(event);
    }
}

@Service
public class KafkaPublishingService {

    private final KafkaTemplate<String, OrderAccepted> kafkaTemplate;

    @Transactional("kafkaTransactionManager")
    public void publishInKafkaTransaction(OrderRequested event) {
        kafkaTemplate.send(
                "orders.accepted",
                event.orderId(),
                new OrderAccepted(event.orderId(), event.eventId())
        ).join();
    }
}
~~~

This is a **conceptual structure**: the code illustrates two separate services so Spring proxies apply the two transaction managers. Constructors, repositories, bean names, propagation, and producer factory must be configured in the actual application. Do not copy this pattern into a transactional Kafka listener that already has an outer transaction without carefully analyzing transaction nesting.

With the DB transaction on the outer method and the Kafka transaction on the inner method, Kafka can commit when the inner method completes, before the outer DB transaction commits. Yet this is **still not an atomic commit**:

~~~text
BEGIN DB transaction
    INSERT order
    BEGIN Kafka transaction
        SEND OrderAccepted
    COMMIT Kafka transaction  -> succeeds
COMMIT DB transaction         -> fails
~~~

Result: downstream consumers may already have read `OrderAccepted` even though the database has no order. Kafka-first only **shifts the failure window** in the opposite direction; it does not eliminate the dual-write problem.

When the DB is the source of truth, reversing the commit order usually does not satisfy the requirement that events reflect committed DB state.

## 12. Are chained transaction managers 2PC?

Some legacy projects use the **chained transaction manager** pattern to coordinate two transaction managers in a commit order. Spring Kafka previously provided **ChainedKafkaTransactionManager** (deprecated in older releases), or projects may rely on equivalent chaining mechanisms.

Remember: chaining **does not turn Kafka and a database into an XA two-phase commit**. Chaining only starts/commits/rolls back local transactions sequentially. If the first manager commits and the second manager fails, the first manager cannot automatically roll back.

~~~text
DB local transaction ----- COMMIT -> completed
Kafka local transaction -- COMMIT -> failed

No atomic global prepare+commit
across both resources.
~~~

Therefore, do not choose a chained manager just because its name sounds like a distributed transaction. When upgrading Spring Kafka, prefer supported transaction synchronization, understand the commit order, and plan for partial commit handling.

## 13. How does Spring transaction synchronization work?

Spring manages transaction resources and synchronization callbacks in thread context. When a DB transaction is active, a transactionally configured `KafkaTemplate` can synchronize the Kafka transaction with the outer transaction lifecycle instead of committing immediately on each send.

~~~text
Spring DB @Transactional boundary
    |
    +-- TransactionSynchronizationManager
    |
    +-- DB connection / EntityManager
    |
    +-- KafkaTemplate participates in transaction synchronization
    |
    v
DB commit
    |
    v
Kafka transaction completion via synchronization
~~~

This feature reduces manual commit-coordination code. However:

- Transaction context is normally bound to a thread.
- An `@Async` method running on a different thread does not automatically inherit the caller's transaction context.
- A `KafkaTemplate` backed by a non-transactional `ProducerFactory` can produce outside the transaction.
- A different transaction manager selected by `@Transactional` changes the actual boundary.
- External APIs do not participate in transaction synchronization simply because they are called inside a transactional method.

Do not rely on `ThreadLocal` transaction context as an end-to-end guarantee when a listener hands off work to an executor or `CompletableFuture` and returns before the work completes.

## 14. Consumer-initiated Kafka transactions and DB side effects

With a transactional Kafka listener container, a common setup is:

~~~text
Kafka BEGIN K1
    |
    +-- DB BEGIN D1
    |     |
    |     +-- update order
    |     +-- insert audit row
    |     |
    |     v
    |   DB COMMIT D1
    |
    +-- Kafka outputs and source offset
    |
Kafka COMMIT K1
~~~

If D1 fails before commit and the exception propagates out, the container rolls back K1. However, if D1 commits successfully and then K1 aborts, the DB state does not roll back.

Another point is that the **consumed offset** is also part of the Kafka transaction. If K1 aborts, the consumer group may reprocess the same input even though the DB write already committed. This makes DB idempotency even more critical.

Do not place `consumer.commitSync()` inside a transactional listener to try to advance offsets after a DB write, because doing so can commit offsets outside the Kafka transaction and break Kafka consume-process-produce semantics.

## 15. DB idempotency: necessary but not sufficient

In an at-least-once system or one with retries, a Kafka event can be processed multiple times. A common approach is a `processed_events` table with a unique event ID:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Within the same DB transaction, the service attempts to insert the event ID and only applies DB side effects if the event has not yet been processed.

With PostgreSQL, you can use:

~~~sql
INSERT INTO processed_events(event_id)
VALUES (:event_id)
ON CONFLICT (event_id) DO NOTHING;
~~~

The application checks the number of inserted rows to determine whether the event is new or a duplicate. The database unique constraint is the primary guard against race conditions; merely calling `existsById()` before inserting **is not safe when multiple consumers process concurrently**.

However, using `processed_events` alone without storing Kafka publish state can cause **missing output**:

~~~text
Attempt 1:
  INSERT processed_events(E123) -> DB COMMIT
  Kafka COMMIT -> FAILED

Attempt 2:
  processed_events(E123) already exists
  skip all logic

orders.accepted is missing event E123
~~~

To avoid losing events, you must ensure that once DB state is written, the system still has a **durable** way to emit the Kafka output if the first commit fails. Transactional outbox is one way to solve this.

## 16. Transactional outbox: a solution for DB-first reliability

**Transactional outbox** does not attempt to commit DB and Kafka at the same time. Instead, it writes two things **within the same DB transaction**:

1. Business state, such as the `orders` record.
2. An outbox event describing the Kafka message to publish.

~~~text
Kafka input
    |
    v
Spring service
    |
    v
BEGIN DB TRANSACTION
    |
    +-- UPDATE/INSERT orders
    +-- INSERT outbox_events
    +-- INSERT processed_events (if needed)
    |
COMMIT DB TRANSACTION
    |
    v
Outbox relay / CDC
    |
    v
Kafka orders.accepted
~~~

If the DB transaction rolls back, neither the state nor the outbox event exists. If the DB commits, the event to be published is durably persisted even if the Kafka broker or application process is temporarily unavailable.

This eliminates the window where **the DB is committed with no record of the event to publish**, which exists when sending directly to Kafka inside the same service via commit synchronization.

Outbox does not by itself guarantee that a Kafka event is published only once. The relay can publish and crash before marking the outbox row as sent. Therefore, outbox typically provides **at-least-once publish**, and downstream consumers require idempotency.

## 17. Designing the outbox table

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
);

CREATE INDEX idx_outbox_unpublished
ON outbox_events (created_at)
WHERE published_at IS NULL;
~~~

Each field serves a specific purpose:

| Field | Purpose |
|---|---|
| id | Immutable event ID for deduplication and tracing |
| aggregate_id | Kafka key to help preserve ordering per aggregate when appropriate |
| event_type | Event type, used for routing/schema |
| payload_json | Prepared event payload to publish |
| created_at | Timestamp when the event was created in the DB |
| published_at | Marker indicating the relay confirmed a successful Kafka publish |

In systems with multi-tenancy, schema versioning, correlation IDs, or compliance requirements, corresponding metadata columns can be added. Do not store sensitive data in the outbox payload without appropriate encryption and retention policies.

An outbox event should keep an **immutable ID** across all publish retries. If the relay generates a new event ID on every retry, downstream deduplication becomes difficult.

## 18. Writing business state and outbox in one DB transaction

The following service illustrates a DB-only transaction:

~~~java
@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    @Transactional("dbTransactionManager")
    public void accept(OrderRequested event) {
        Order order = Order.from(event);
        orderRepository.save(order);

        OutboxEvent outboxEvent = OutboxEvent.orderAccepted(
                event.eventId(),
                order.getId(),
                order.getStatus());

        outboxRepository.save(outboxEvent);
    }
}
~~~

Here `KafkaTemplate` **does not need to be called inside the DB transaction**. Both `Order` and `OutboxEvent` commit or roll back together under the database transaction manager.

This code is illustrative; production requires combining unique constraints/processed event IDs, deterministic event IDs, and duplicate-input policies. If a source Kafka record is replayed, the service must avoid inserting duplicate outbox events with different IDs and avoid repeating business side effects.

If the input event has a unique `eventId`, it can be used as part of the idempotency key while saving state and the outbox event in the same transaction.

## 19. Outbox relay: polling and CDC

There are two common implementation groups.

### Polling relay

A background worker reads unpublished outbox rows:

~~~text
SELECT unpublished outbox rows
       |
       v
KafkaTemplate.send(...)
       |
       +-- failure --> keep row for retry
       |
       v
Kafka broker acknowledge
       |
       v
UPDATE outbox.published_at
~~~

In PostgreSQL, when multiple relay workers run concurrently, **FOR UPDATE SKIP LOCKED** or an appropriate claim/lease mechanism can reduce contention. However, avoid holding a DB transaction or row lock open for a long time while waiting for a Kafka network send.

A safer flow typically uses a timeout/lease-based claim, publishes, confirms the result, and then marks completion; if the worker crashes before marking, the row is reclaimed after the lease expires and may be published again. Therefore, downstream consumers must be idempotent.

### Change Data Capture (CDC)

A CDC connector such as Debezium can read the database transaction log and stream outbox changes to Kafka. In that case, the service does not need to poll a SQL table itself to emit events.

~~~text
DB COMMIT orders + outbox
         |
         v
Database transaction log
         |
         v
CDC connector
         |
         v
Kafka orders.accepted
~~~

CDC reduces polling logic in the application, but you still need to operate the connector, schemas, offsets, error handling, and idempotent downstream processing. Do not assume CDC turns the DB and Kafka into a global XA transaction.

## 20. Why can an outbox still produce duplicate publishes?

Consider a polling relay:

~~~text
1. Relay reads outbox row E123.
2. Relay publishes E123 to Kafka.
3. Broker acknowledges successfully.
4. Relay crashes before UPDATE published_at.
5. Relay restarts and sees E123 is still unpublished.
6. Relay publishes E123 again.
~~~

Kafka may contain two records with the same event ID `E123`. This behavior is acceptable when the architecture is designed for at-least-once delivery with deduplication.

To keep this under control:

- Use a stable event ID in the key/header/value.
- Enable producer idempotence and appropriate acknowledgements, but do not confuse producer idempotence with end-to-end business deduplication.
- Downstream consumers should store the processed event ID in the same transaction as the side effect.
- Do not let the relay change the event ID on retries.
- Monitor outbox backlog, oldest event age, and publish failures.

If business requirements forbid duplicate outputs even at the Kafka log level, you must analyze transaction boundaries, relay ownership, and database deduplication more deeply. A DB outbox row alone does not provide exactly-once log append to Kafka.

## 21. Comparing transaction synchronization and outbox

| Criterion | DB + Kafka synchronization | Transactional outbox |
|---|---|---|
| When is Kafka sent? | Usually right inside the service transaction | After DB commit via relay/CDC |
| Atomic DB + Kafka commit? | **No** | **No**, but DB state + outbox intent are atomic |
| DB commits then Kafka commit fails | Risk of missing event; requires recovery | Event intent remains in DB for relay retry |
| Kafka outage | May fail business path or cause commit errors | DB can commit event intent; relay waits for Kafka |
| Kafka output latency | Can be low when both systems are healthy | Adds relay/CDC delay |
| Operational infrastructure | Transaction managers, Kafka producer, compensation | Outbox table, relay/CDC, monitoring, and cleanup |
| Duplicate events | Can occur on retries/uncertain commits | Can occur on relay retries |
| Durability on process crash | Must design commit-gap handling | Event intent persists in DB if DB committed |
| When suitable | Partial-failure policy and reconciliation are acceptable | Events must never be lost after DB state commits |

If the DB is the source of truth and Kafka events are required so other systems stay updated accurately, outbox generally achieves **recoverable eventual consistency** more easily than relying solely on synchronization callbacks.

If the workload is purely Kafka-to-Kafka with no DB side effects, a Kafka transaction with consumed offsets may be the natural choice, with no outbox needed.

## 22. Transaction timeouts, DB locks, and Kafka polling

When a DB transaction and a Kafka transaction coexist, processing time can be constrained by multiple timeouts:

| Parameter | Scope |
|---|---|
| Kafka transaction.timeout.ms | Maximum time a Kafka transaction may remain open per producer/broker config |
| Consumer max.poll.interval.ms | Maximum interval between polls per the consumer group protocol |
| DB transaction timeout | Time allowed by the database/Spring for a transaction to execute |
| SQL lock timeout | Time spent waiting for a database lock |
| HTTP client timeout | Time spent calling an external service |

A transaction delayed while waiting on a DB lock can cause the Kafka transaction to time out. If the consumer does not poll frequently enough, the group may rebalance and transfer partition ownership. When committing consumed offsets inside a Kafka transaction, membership changes or producer fencing can cause the commit to fail.

Do not raise every timeout indefinitely to "avoid errors." Identify the bottleneck: slow SQL, lock contention, Kafka coordinator, network, oversized batches, or long-running listener logic.

Recommended practices:

- Keep DB transactions short; avoid long external API calls inside DB transactions.
- Do not wait on long retry backoffs while a Kafka transaction remains open.
- Measure transaction duration, lock wait, Kafka commit latency, and consumer poll interval.
- Limit `max.poll.records`/batch size based on actual processing time.
- Test graceful shutdown, rebalance, and restart while transactions are in flight.

## 23. Kafka consumer ownership and DB write retries

When a listener is transactional, an exception propagating to the container rolls back the Kafka transaction. Afterwards, Spring Kafka can use **DefaultAfterRollbackProcessor** to seek/retry the record according to a `BackOff`.

~~~text
Consumer A receives orders.requested/P1@80
       |
       +-- Kafka transaction K1
       +-- DB transaction D1
       |
       +-- DB COMMIT D1 succeeds
       |
       +-- Kafka K1 abort/fail
       |
       v
Record P1@80 may be reprocessed
       |
       v
DB needs idempotency and Kafka output needs recovery
~~~

If a group rebalance occurs during this interval, another consumer can take over the partition and process the same event. **Do not rely on Kafka having a single partition owner at a steady-state point to infer that a DB side effect only runs once.**

For non-idempotent operations such as crediting money, deducting inventory, or sending invoices, use an event ID/transaction ID and check business state inside the DB transaction.

After multiple retries, the record may be routed to a DLT. However, **a DLT only proves the record could not be processed under the retry policy**; it does not guarantee the database rolled back or had no side effects. The DLT handler must inspect DB state before replaying.

## 24. DLT and recovery when the DB has already committed

Suppose:

~~~text
orders.requested/P1@80
   |
   +-- DB COMMIT order O-1001
   |
   +-- Kafka COMMIT fails
   |
   v
AfterRollbackProcessor retries multiple times
   |
   v
Record is sent to DLT
~~~

At the DLT stage, the business order may **already exist in the database**. If an operator sees the DLT record and replays it by inserting a new order, there is a risk of duplicates or unique constraint errors.

A recovery procedure should:

1. Read the original topic, partition, offset, and event ID from the DLT.
2. Check whether the DB already has the corresponding business state.
3. Check whether the Kafka output already committed or was published by another retry.
4. Determine whether only the output is missing, only the DB is missing, or both already succeeded.
5. Choose an idempotent, audited compensation/replay action.
6. Avoid blindly retrying the entire listener when part of the side effects already committed outside Kafka.

With an outbox, a durable event intent in the DB makes identifying unpublished outputs much easier: the relay can keep retrying until published, or an operator can resolve the error explicitly.

## 25. Observability for dual-write pipelines

A system coordinating Kafka and a DB should monitor **both transaction outcomes** rather than only logging listener success/error.

Metrics to include:

- DB transaction commit/rollback counts and p95/p99 duration.
- Kafka transaction commit/abort counts and commit errors.
- Consumer lag by topic/partition.
- Producer send errors, request latency, and transaction coordinator errors.
- Count of Kafka commit failures after DB commit.
- Count of records retried after DB commit.
- Count of business events missing outputs detected by reconciliation.
- Outbox backlog, event age, relay throughput, and publish failures if using an outbox.
- DLT count, replay success/failure, and duplicate processing attempts.

An example structured log:

~~~text
eventId=E123
orderId=O-1001
inputTopic=orders.requested
inputPartition=1
inputOffset=80
dbOutcome=committed
kafkaOutcome=commit_failed_or_unknown
recoveryState=pending_reconciliation
~~~

This is an illustrative application log format. Do not use event IDs or offsets as high-cardinality metric labels; put them in logs/traces for investigation.

On a transaction commit timeout, avoid blindly logging "Kafka definitely aborted" when the actual status has not been verified. Check committed offsets, event IDs on the output topic, or relay state to decide the next action.

## 26. Reconciliation: detecting inconsistencies after they occur

No distributed system architecture should rely solely on the happy path. With DB-first direct produce, a **reconciliation job** can compare DB state against event/outbox publish state.

Example:

~~~text
Database:
  order O-1001 status=ACCEPTED

Kafka output:
  OrderAccepted(eventId=E123) not found

Reconciliation:
  check durable publish state
  determine that the event needs to be republished
  publish with idempotency key E123
~~~

If you only scan the Kafka topic for an event, note that retention may have deleted older records and offsets are not business keys. A reliable outbox table or published-event audit store gives reconciliation a clearer determination of the outcome.

Reconciliation must also guard against the case where **the Kafka event already committed but the acknowledgement was lost**. Republishing with a stable event ID paired with downstream deduplication is generally safer than assuming no event exists.

Do not auto-delete DB rows whenever a Kafka output is not found; that is a business compensation operation that can cause data loss and requires evaluating final system state.

## 27. Testing transaction synchronization

Use a **real Kafka broker in tests** (such as Testcontainers Kafka or EmbeddedKafka) and a database matching production whenever possible. You cannot prove commit order and failure windows with unit tests that only mock `KafkaTemplate`.

### Test 1: Both DB and Kafka succeed

1. Send `OrderRequested` with event ID `E123`.
2. Wait for the listener to execute and complete all commits.
3. Verify the DB contains the order.
4. Verify a `read_committed` consumer receives `OrderAccepted`.
5. Verify the consumed offset advances properly if the container is transactional.

### Test 2: DB rolls back before Kafka commit

1. Simulate a SQL error or constraint violation.
2. Let the exception propagate out of the transaction boundary.
3. Verify the DB transaction did not commit.
4. Verify Kafka outputs from the failed transaction are not visible to `read_committed`.
5. Verify the input record is retried/recovered as configured.

### Test 3: Kafka commit fails after DB commit

1. Inject a fault at the Kafka commit stage.
2. Ensure the DB commit succeeded.
3. Confirm the application records the Kafka commit failure/unknown state.
4. Verify reprocessing does not create duplicate DB side effects.
5. Verify the pipeline has a mechanism to recover the missing output event.

This is the most critical failure scenario; a test that only makes `KafkaTemplate.send()` throw before the DB commit **does not simulate** a commit failure occurring after the DB commit.

### Test 4: Crash between the two commits

1. Stop the process after the DB commit but before the Kafka commit when the test harness supports it.
2. Restart the application with the same group.
3. Confirm the DB state persists.
4. Confirm the source record can be read again.
5. Verify idempotency and output recovery.

### Test 5: Outbox relay crash

1. Commit business state and the outbox event in the same DB transaction.
2. Have the relay publish the Kafka event.
3. Simulate a crash before marking `published_at`.
4. Let the relay process again.
5. Confirm the event ID is immutable and downstream does not create duplicate side effects.

### Test 6: Rebalance and transaction timeout

1. Run multiple consumer replicas.
2. Make the listener take longer or trigger a rebalance during processing.
3. Observe Kafka transaction abort/fencing or commit failure.
4. Verify the DB handles redelivered records safely.
5. Confirm the system loses no events after recovery.

Do not use fixed sleeps to infer transaction completion; wait on conditions with timeouts and verify both DB and Kafka state.

## 28. Common design mistakes

| Mistake | Why it is dangerous | Alternative |
|---|---|---|
| Assuming `@Transactional` covers Kafka and DB atomically | Two managers commit independently | Understand commit order; use outbox when events must not be lost |
| Skipping Kafka output if DB record already exists | DB committing before Kafka commit can leave a missing event | Store an outbox event or durable publish state |
| Committing Kafka before DB to be "safer" | Can emit events when the DB rolls back | Choose commit order by semantics; do not treat it as 2PC |
| Swallowing listener exceptions | Container may commit the Kafka transaction despite business failure | Rethrow errors that require rollback |
| Using a non-transactional producer in a transactional Kafka listener | Outputs may commit outside the consumed-offset transaction | Use a `KafkaTemplate`/`ProducerFactory` participating in the same transaction |
| Manually committing consumer offsets inside the listener | Breaks atomicity of offsets + Kafka outputs | Let the container invoke `sendOffsetsToTransaction` |
| Writing to DB then sending to Kafka without durable recovery | Leaves an event-loss window after DB commit | Transactional outbox or durable reconciliation |
| Retrying infinitely during a Kafka outage | Holds threads/DB locks and increases lag | Finite backoff, outbox relay, and alerts |
| Keeping a DB transaction open during slow API calls | Lock contention, timeouts, and rebalances | Short transactions and idempotent workflows |
| Replaying DLT without checking the DB | Can repeat already-committed side effects | Audit event ID, inspect DB/output, and replay with control |

## 29. Choosing an architecture by requirement

| Business requirement | Suitable approach |
|---|---|
| Consume Kafka and produce Kafka, no DB writes | Consumer-initiated Kafka transaction with consumed offsets |
| DB state and Kafka event must stay consistent after failures | Transactional outbox + relay/CDC + idempotent consumer |
| DB-first direct produce where missing events can be reconciled | Transaction synchronization + durable reconciliation |
| Multiple services, APIs, and DBs in a workflow | Saga/state machine, outbox, and per-step idempotency |
| Events require ordering per aggregate | Kafka key by aggregate ID, outbox ordering policy, and downstream version check |
| Duplicate side effects must not occur | Unique event ID, DB unique constraint, and idempotent handler |

If using Spring transaction synchronization, design documentation should explicitly state which manager is outer, which is inner, the commit order, exception propagation behavior, and how to recover when the second commit fails. These details matter far more than simply listing `@Transactional` annotations in code.

## 30. Reliable implementation checklist

For a pipeline combining Spring Kafka and a database:

1. Determine whether the DB or Kafka is the source of truth for business state.
2. List all side effects: SQL writes, Kafka outputs, REST APIs, emails, caches.
3. Identify the transaction manager and actual boundary of each side effect.
4. If using Kafka container transactions, ensure `KafkaTemplate`, `ProducerFactory`, and consumed offsets share the same Kafka transaction.
5. If using DB transactions, specify the right qualifier and verify calls go through the Spring proxy.
6. Document the DB-first/Kafka-first commit order and failure window.
7. Do not rely on synchronization as an atomic distributed transaction.
8. Use a transactional outbox if you cannot allow a successful DB commit to lose the event to be published.
9. Use stable event IDs, unique constraints, and idempotent side effects.
10. Ensure downstream Kafka consumers use `read_committed` if they must skip aborted transactional outputs.
11. Configure retries, DLT, and reconciliation for both Kafka commit failures and database failures.
12. Monitor DB/Kafka commit outcomes, outbox backlog, DLT, and recovery latency.
13. Test crashes between the two commits, DB rollbacks, Kafka commit failures, rebalances, and duplicate delivery.

**Synchronizing Kafka transactions with DB transactions** in Spring Kafka mainly serves to **coordinate two local transactions in a defined order**. It does not make database and Kafka commits strictly atomic. For Kafka-to-Kafka flows, a Kafka transaction can commit outputs and consumed offsets together. However, when business state lives in a database, a failure window remains after one commit succeeds and before the other completes. When the requirement is **zero lost events after the DB has committed**, transactional outbox combined with idempotency and reconciliation is generally a more reliable foundation than merely enabling `@Transactional` and transaction synchronization.
