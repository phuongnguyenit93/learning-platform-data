# Kafka-first commit order

In a Spring Kafka application that interacts with both **Apache Kafka** and a **database**, the commit order between the two resources determines what happens when one succeeds and the other fails. **Kafka-first commit order** means **the Kafka transaction is committed before the database transaction**. This differs from the common model where the database commits first and Kafka commits afterward.

This is a reliability problem, not merely a method call ordering question. Two distinct transaction managers do not automatically form an atomic distributed transaction. Even if the application commits Kafka before committing the database, there is still a time window during which the two systems' states are inconsistent; if the second commit fails, the first commit **is not automatically rolled back**.

This lesson focuses on Spring Kafka, Spring transaction management, and transactional databases such as PostgreSQL/MySQL. It is essential to distinguish a **producer-initiated transaction** (a service receives a command and initiates a Kafka event) from a **consumer/container-initiated transaction** (a listener container manages the Kafka transaction and consumer offsets). The two contexts have different boundaries and configurations.

## 1. Why does commit order matter?

Suppose a service creates an order:

1. Save the Order to the database.
2. Publish OrderCreated to Kafka.
3. Complete the request.

Desired business state:

    Database:
      orders[id=O-123, status=CREATED]

    Kafka:
      orders.events -> OrderCreated(orderId=O-123)

If only one of the two operations commits, an inconsistent state can arise:

- Kafka has OrderCreated, but the database does not have the Order.
- The database has the Order, but Kafka does not have OrderCreated.

The system must decide which temporary condition is acceptable, how to detect divergence, how long divergence may last, and how to recover after failure.

Commit order does not eliminate the failure window; it only **shifts the failure window**:

| Order | Commit 1 | Commit 2 | If commit 2 fails |
|---|---|---|---|
| DB-first | Database | Kafka | Database changed; Kafka event may not be published |
| Kafka-first | Kafka | Database | Kafka event published; database may roll back |

No commit order guarantees atomicity across two resource managers if you only coordinate independent Spring transaction managers.

## 2. Which transactions are we talking about?

A Kafka producer transaction lets an application group multiple Kafka writes and commit or abort them together. When the Kafka transaction commits, the records become committed for downstream consumers configured with isolation.level=read_committed.

A database transaction groups SQL operations such as INSERT/UPDATE/DELETE and commits or rolls them back on the database.

These two transactions have different scopes:

    KafkaTransactionManager:
      begin -> KafkaTemplate.send(...) -> commit Kafka

    DataSourceTransactionManager / JpaTransactionManager:
      begin -> repository.save(...) -> commit database

When the same business operation invokes both, seeing the word "transaction" twice does not mean the two systems share an atomic commit protocol.

This setup is **not** equivalent to XA/two-phase commit:

    TransactionManager A (Kafka)  -----> Broker
    TransactionManager B (JPA)    -----> Database

Once the Kafka transaction has committed, a subsequent DB error cannot turn the earlier Kafka transaction back into aborted.

## 3. How does Kafka-first happen?

With Kafka-first, the expected flow is:

    Receive CreateOrder command
               |
               v
    Begin database transaction
               |
               v
    Insert order row (uncommitted)
               |
               v
       Begin Kafka transaction
               |
               v
       Send OrderCreated event
               |
               v
       COMMIT Kafka transaction
               |
               v
       COMMIT database transaction
               |
               v
          Return success

At the moment Kafka commits while the database has not committed yet, downstream consumers can read OrderCreated before the INSERT becomes visible to other DB connections.

If the database commits successfully right afterward, the final state is consistent. If the database commit fails, the already-committed OrderCreated event does not disappear on its own.

This is the core characteristic of Kafka-first: **Kafka is the system that completes its commit earlier, and the database is the system that can fail afterward**.

## 4. Failure windows of Kafka-first

Suppose the database transaction has not committed yet, while the Kafka transaction has committed. Several scenarios can occur:

| Failure point | Kafka | Database | Consequence |
|---|---|---|---|
| Before Kafka send | Uncommitted | Uncommitted | Both can be rolled back |
| Kafka send fails before commit | Kafka TX aborts/fails | DB TX can roll back | Must not report success |
| Kafka commit succeeds, DB pending | Event committed | Order uncommitted | Downstream reads event too early |
| DB commit fails after Kafka commit | Event committed | Expected DB change missing | **Orphan event / inconsistency** |
| DB commit succeeds, response lost | Event committed | Order committed | Client retry may create duplicate command |
| Kafka commit outcome uncertain | Confirmation uncertain | DB decides per exception/flow | Needs reconciliation; do not guess by timeout |

A common mistake is seeing KafkaTemplate.send() return a successful future and calling that "Kafka committed." Send success does not necessarily mean transaction commit. With a transactional producer, downstream read_committed consumers consider outputs committed only after the transaction commit succeeds.

Another mistake is thinking a DB rollback triggers a Kafka rollback after Kafka has already committed. That is not true for two separate transactions.

## 5. How do DB-first and Kafka-first differ?

In a Spring Kafka application using transaction synchronization, **DB-first** is typically the default when an outer @Transactional database method invokes a KafkaTemplate participating in a transaction synchronized with the database transaction: the database commits first, then Kafka commits. Exact details depend on the transaction manager setup and Spring version.

If you want **Kafka-first**, do not simply reorder lines:

~~~java
repository.save(order);
kafkaTemplate.send("orders.events", event);
~~~

Inside a database transaction, repository.save() does not mean DB commit. Likewise, send() does not mean Kafka commit. **Method call** order and **transaction commit** order are two separate things.

Comparison:

    DB-first:
      save() -> send()
      commit database -> commit Kafka

    Kafka-first:
      save() -> send() in a separate transaction
      commit Kafka -> commit database

For Kafka-first, transaction boundaries must be structured so that the **inner Kafka transaction completes** before the outer database transaction completes.

## 6. Nested @Transactional pattern for Kafka-first

A technique commonly described in Spring Kafka is using **two separate @Transactional methods**, where:

- The outer method opens a database transaction.
- The inner method opens a Kafka transaction.
- The inner method returns after the Kafka transaction has committed.
- The outer method finishes later, so the database commits after Kafka.

Diagram:

    Outer method: @Transactional("dbTransactionManager")
      |
      +-- DB save/update
      |
      +-- Inner bean method: @Transactional("kafkaTransactionManager")
      |        |
      |        +-- KafkaTemplate.send(...)
      |        |
      |        +-- Kafka COMMIT when inner method completes
      |
      +-- DB COMMIT when outer method completes

These are **two local transactions coordinated in sequence**, not a distributed transaction. Be prepared for the case where the inner Kafka commit succeeds and the outer DB commit fails.

## 7. Code example with two Spring beans

Suppose the application receives an order-creation command outside Kafka, such as a REST request. The example below uses separate beans so the Spring AOP transaction proxy actually intercepts the inner method call.

### 7.1. Service responsible only for publishing inside a Kafka transaction

~~~java
@Service
public class OrderKafkaPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderKafkaPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
        // When the method returns, KafkaTransactionManager commits.
    }
}
~~~

KafkaTemplate must use a transaction-capable ProducerFactory matching kafkaTransactionManager. Calling send() inside the method does not guarantee the final outcome: if the producer fails to send or commit fails, the Kafka transaction may not commit successfully.

### 7.2. Service opening the outer database transaction

~~~java
@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;
    private final OrderKafkaPublisher publisher;

    public OrderCommandService(
            OrderRepository orderRepository,
            OrderKafkaPublisher publisher) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(CreateOrder command) {
        OrderEntity entity = new OrderEntity(
            command.orderId(),
            command.amount()
        );

        orderRepository.save(entity);

        OrderCreated event = new OrderCreated(
            command.eventId(),
            command.orderId(),
            command.amount()
        );

        // Called via another bean: Kafka transaction commits first.
        publisher.publish(event);

        // Only when createOrder() returns does the DB transaction commit.
    }
}
~~~

Assume the OrderEntity, CreateOrder, and OrderCreated classes are already defined in the application; this example only shows transaction structure.

**Important note:** calling publisher.publish(event) is not a nested call inside the same Spring bean. If you place both methods in the same class and call this.publish(), the default Spring proxy may not intercept self-invocation; consequently, @Transactional on the inner method may not be applied.

### 7.3. Successful execution flow

    OrderCommandService.createOrder()
      DB TX begin
        INSERT order
        OrderKafkaPublisher.publish()
          Kafka TX begin
          Kafka send
          Kafka TX commit
        return from publisher.publish()
      DB TX commit
    return from createOrder()

Here the Kafka commit actually occurs before the database commit if the Kafka transaction manager and Spring proxies behave as designed.

## 8. Configuring KafkaTransactionManager and DB transaction manager

The ProducerFactory configuration must support transactions. Spring Boot example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-command-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        acks: all
        enable.idempotence: true
~~~

With proper Spring Boot auto-configuration, transaction-id-prefix can enable automatic creation of KafkaTransactionManager. If the application defines transaction managers explicitly, ensure the bean names match those referenced in @Transactional.

Kafka manager example:

~~~java
@Bean("kafkaTransactionManager")
KafkaTransactionManager<String, OrderCreated> kafkaTransactionManager(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

JDBC example:

~~~java
@Bean("dbTransactionManager")
DataSourceTransactionManager dbTransactionManager(
        DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

If the system uses JPA/Hibernate, you typically need JpaTransactionManager matching EntityManagerFactory instead of DataSourceTransactionManager. Do not register multiple unnecessary managers simultaneously and assume repositories will pick the right one; configure the transaction manager and persistence stack consistently.

Different Spring Boot/Spring Framework versions have different default bean naming or primary transaction manager mechanisms. Explicitly specifying transactionManager = "..." in examples clarifies the intended commit order.

## 9. Pitfall: @Transactional might not actually apply

Common mistakes that prevent Kafka-first from actually working:

- **Self-invocation:** the same bean calls the inner method via this, so the Spring proxy does not create the expected transaction.
- **Unproxied method:** improper proxy configuration, visibility, or lifecycle.
- **Wrong manager selected:** annotation omits the manager name in a project with multiple PlatformTransactionManager beans.
- **Non-transactional ProducerFactory:** KafkaTemplate does not start or join a Kafka transaction as intended.
- **Template pointing to a different factory:** inner publisher uses a KafkaTemplate backed by a non-transactional producer factory.
- **Method returning a future before Kafka work completes:** transaction boundary and async work do not align.
- **Exception caught and swallowed:** outer DB method still commits even though the inner transaction failed.
- **Pre-existing transaction from the caller:** propagation and transaction synchronization make the order more complex than expected.

Verify with integration tests that observe actual Kafka output and database commit states under injected failures. Simply reading log order from repository.save() and kafkaTemplate.send() does not prove commit order.

## 10. If Kafka commit succeeds but DB commit fails

This is the signature failure mode of Kafka-first.

    DB TX: INSERT order O-123 (uncommitted)
             |
             v
    Kafka TX: publish OrderCreated(O-123)
             |
             v
    Kafka commit SUCCESS
             |
             v
    DB commit FAIL: deadlock / constraint / disconnect
             |
             v
    Kafka has the event, DB lacks the order

A downstream service may receive the event and immediately call the Order API. It gets a 404 or sees no existing state.

You cannot fix this by issuing a rollback on the already-committed Kafka transaction. Options must be designed ahead of time:

1. **Compensation event:** publish OrderCreationFailed/OrderCancelled if business rules allow compensation. Compensation is a new action, not erasing the old event.
2. **Reconciliation:** the system periodically checks events against the database, detects orders missing a row, and recovers or alerts.
3. **Event-first architecture:** treat the Kafka event as the primary input record; the database is a materialized projection that can be updated later.
4. **Outbox:** if the database is the source of truth, writing the event to an outbox in the same DB transaction and publishing after DB commit is usually more appropriate.
5. **Consumer tolerance:** downstream retries DB queries when events arrive ahead of commit, with bounded timeouts and a distinction between "not yet committed" and "DB will never commit."

Choose the strategy according to business requirements. A few seconds of downstream 404 retries can handle a slow DB commit, but cannot fix a DB transaction that rolled back permanently.

## 11. If Kafka commit fails before DB commit

In the nested transactions model above, if the inner Kafka transaction throws an exception during send/commit, the exception can propagate to the outer database method and cause the DB to roll back.

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(CreateOrder command) {
    orderRepository.save(toEntity(command));
    publisher.publish(toEvent(command)); // May throw an exception.
}
~~~

If publisher.publish() fails, the outer method does not complete normally; the Spring DB transaction interceptor can roll back according to the configured rollback rules.

Keep in mind:

- For RuntimeException, Spring transactions roll back by default.
- For checked exceptions, default rollback rules can differ; use rollbackFor as needed.
- If code catches the exception without rethrowing or marking rollback-only, the DB can commit even though Kafka failed.
- For commit errors due to timeout/network, the client may not know whether the broker committed. Never conclude for sure that no event exists just because the method threw a timeout.

An explicit configuration can declare rollbackFor:

~~~java
@Transactional(
    transactionManager = "dbTransactionManager",
    rollbackFor = Exception.class
)
public void createOrder(CreateOrder command) throws Exception {
    orderRepository.save(toEntity(command));
    publisher.publish(toEvent(command));
}
~~~

However, rollbackFor does not solve the case where Kafka committed and the database subsequently failed; it only controls rollback behavior of the current transaction when an exception occurs within its execution scope.

## 12. Uncertain errors and idempotency

Distributed systems have an important state: **uncertainty about whether a commit occurred**.

For example, the Kafka commit succeeds on the broker, but the response to the client is lost. The application may receive a timeout or exception. If it automatically retries the entire command, it may publish another event in a new Kafka transaction.

Therefore:

- Attach a stable business eventId to each command.
- Do not generate a new eventId just because a client retries a request.
- Use a request-id or idempotency key for business identification.
- Downstream consumers must be idempotent by eventId/commandId.
- Store audit/reconciliation records for handling decisions made during uncertain states.

Kafka producer idempotence handles retries at the producer protocol level within Kafka client capabilities; it does not understand that two user CreateOrder requests represent the same business operation.

An endpoint may need to return a "processing/unknown" status and let the client query the result by commandId, rather than promising that failure means no event was published.

## 13. Downstream reading the event before the database commits

Kafka-first introduces a race condition even when both transactions eventually succeed.

    Thread 1 — OrderCommandService
      10:00:00.000 DB insert uncommitted
      10:00:00.010 Kafka TX commit
      10:00:00.040 DB TX commit

    Thread 2 — OrderConsumer
      10:00:00.020 Reads OrderCreated from Kafka
      10:00:00.025 Queries DB for Order
      10:00:00.026 Row not found (uncommitted)

If downstream depends on the database record already existing as soon as the event appears, Kafka-first can violate that assumption.

Design approaches:

- Include the required data directly inside the event so downstream does not have to query the source DB.
- Choose events that describe **intent** or eventually consistent state rather than asserting the DB transaction has committed.
- Allow bounded retries when a lookup does not find the row yet.
- Only publish events after DB commit via an outbox if you must guarantee "event => committed state."
- Use correlation IDs to trace race conditions instead of immediately treating a 404 as permanent data corruption.

Do not use sleep() in the publisher to wait for the database commit; the inner Kafka transaction runs inside the outer DB transaction, so any delay only widens the window.

## 14. Producer-initiated and consumer-initiated transactions differ

In a **producer-initiated** flow (REST request, job, service method):

    REST -> DB outer transaction
                |
                +-> Kafka inner transaction commit
                |
           DB outer commit

The nested method pattern can produce Kafka-first as shown above.

In a **consumer-initiated** flow where the Spring Kafka listener container manages the Kafka transaction:

    Container Kafka TX begin
       |
       v
    @KafkaListener
       |
       +-> DB local transaction begin/commit
       |
       v
    Container Kafka TX commit (includes input Kafka offset if configured properly)

In the container-initiated model, **the Kafka transaction is the outer layer**, opened by the container before calling the listener and committed after the listener finishes. If the listener opens a DB transaction inside, the DB usually commits before Kafka. That is **DB-first** at the two-resource level.

Thus, you cannot simply add @Transactional("kafkaTransactionManager") on an inner method and assume Kafka will commit before the DB when the listener container already has an active Kafka transaction. The inner call may join the existing resource transaction; the outer Kafka transaction will still not commit until the container finishes.

To guarantee a different commit order, redesign the transaction boundaries and test them; do not assume a nested annotation controls the commit timing of an open container transaction.

## 15. Kafka offsets make the situation more complex

If an application consumes Kafka input, writes to a database, and then publishes Kafka output, three states must be considered:

1. Database transaction.
2. Kafka output transaction.
3. Consumer group offset of the input.

In a standard container Kafka transaction, outputs and input offsets can commit **atomically together**. Trying to commit the Kafka transaction before the DB could also commit the input offset before the database commits.

Dangerous example:

    Input order-request@offset 90
       |
       v
    Kafka TX contains output and input offset=91
       |
       v
    Commit Kafka SUCCESS
       |
       v
    Commit DB FAIL

If the Kafka transaction has already committed offset 91, the consumer group may continue from the next record without automatically re-reading offset 90, while the DB side effect never completed. This is no longer merely "event ahead of DB"; it can also **lose the ability to reprocess input by offset**.

Therefore, for consumer-initiated flows, prioritize controlling container transaction boundaries and database idempotency/consistency. Do not mechanically apply a producer-initiated Kafka-first recipe to a listener.

## 16. Comparing architectures when Kafka and DB must stay consistent

| Architecture | Commit order | Atomicity | Suitable for |
|---|---|---|---|
| DB-first synchronization | DB then Kafka | Not atomic across two resources | Accepting reconciliation when Kafka fails |
| Kafka-first nested TX | Kafka then DB | Not atomic across two resources | Event-first, accepting DB eventual consistency |
| Transactional outbox | DB state + outbox in same DB transaction; publisher sends to Kafka later | State and publish intent atomic in DB | DB as source of truth, zero lost events required |
| Transactional inbox | Processed marker + DB state in same DB transaction | DB side effect and dedup atomic in DB | Consumer receiving Kafka input, preventing duplicates |
| Kafka-only transaction | Kafka outputs + input offsets commit in same Kafka TX | Atomic within Kafka | Pure Kafka read-process-write |
| Saga/compensation | Multiple independent steps with compensating events | Eventual consistency | Multi-service workflows, side effects outside Kafka |

If the database is the source of truth and events describe committed changes, **transactional outbox** is usually a much better fit than trying to adjust commit order.

If Kafka events are the canonical event log and the database is a downstream projection, Kafka-first can fit conceptually, but design the DB as a replayable and rebuildable projection rather than assuming DB commits happen simultaneously with events.

## 17. What is the transactional outbox solution?

With an outbox, one database transaction writes both business state and the event to publish:

    Begin DB transaction
       |
       +-> INSERT orders
       |
       +-> INSERT outbox_event(eventId, payload)
       |
    Commit DB transaction
       |
       v
    Outbox publisher reads outbox_event
       |
       v
    KafkaTemplate.send(...)
       |
       v
    Mark outbox as published

Advantage: if the database commits, the event to publish is durably persisted in the outbox; if the database rolls back, neither the Order nor the outbox row takes effect.

Drawback: the publisher can successfully send the event to Kafka and crash before marking the outbox row published. The event can be resent, so downstream still needs idempotency by eventId.

Outbox does not make Kafka sends strictly once across all failure windows; it solves **preventing lost publish intent due to split commits** between the database and Kafka, then relies on at-least-once delivery + deduplication.

## 18. Transactional inbox for consumers writing to a database

For a Kafka consumer that updates a DB, one way to prevent duplicate redelivery effects is to record the eventId marker within the same DB transaction:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside the DB transaction:

~~~text
BEGIN;

INSERT processed_events(consumer_name,event_id,...)
  if not already present;

If event already exists:
  do not reapply side effect;
If new:
  UPDATE/INSERT business data;

COMMIT;
~~~

When a Kafka record is redelivered because the offset was not committed, the consumer sees the existing marker and skips repeating the business update.

Ensure the deduplication statement and DB changes reside **in the same transaction**, with a unique constraint to handle concurrent attempts. Checking existence and writing in two separate transactions risks race conditions.

An inbox does not eliminate the need to commit Kafka offsets; it makes business operations safe under Kafka redelivery.

## 19. When should you use event-first?

Kafka-first is more acceptable when **events are treated as the canonical truth** and the database is state derived from events.

Architectural example:

    Producer command
         |
         v
    Kafka committed event
         |
         v
    Projection consumer
         |
         v
    Database materialized view

In this model, there is no need to nest a Kafka-first transaction inside a DB transaction to create both an event and a row together. It is usually simpler to commit the event to Kafka first, and let an independent consumer read the event and update the DB projection.

If the projection consumer fails, the Kafka event remains the source for replay. The database can recover from the Kafka log given suitable retention and snapshot/rebuild mechanisms.

This approach has trade-offs:

- The database experiences eventual consistency delay.
- Command APIs need a pending-state model or asynchronous queries.
- Projection consumers must be idempotent and have lag monitoring.
- Schema evolution and event retention must support long-term rebuilds.
- Replays must avoid inappropriate side effects.

Event-first does not mean an API that just created an Order can immediately read that Order from the DB. Contracts with clients and downstream systems must reflect this.

## 20. Spring transaction synchronization and commit order

In Spring, a KafkaTemplate with a transactional ProducerFactory can join an active transaction via synchronization. When a database transaction is the outer transaction, bound Kafka resources may be committed after the database per typical synchronization behavior.

This reduces boilerplate for certain paths, but carries risks:

- The database has committed, and the subsequent Kafka commit can fail.
- A Kafka commit exception may be returned to the caller after the DB committed; the caller must recognize the DB already changed.
- Applications must check their Spring Kafka version because exception handling in synchronized commits has changed over releases.
- Transaction synchronization does not turn Kafka and a DB into an atomic distributed transaction.

To intentionally enforce Kafka-first, using an inner method with KafkaTransactionManager and an outer method with a DB transaction manager is a common technique. However, the call must go through a Spring proxy and use the correct resource managers.

Do not rely on historical chained transaction manager patterns as proof of an atomic transaction across Kafka and a DB. A chain of local transaction managers still suffers partial commit failures; many chained APIs have been deprecated and are not preferred for new designs.

## 21. Choosing appropriate transaction propagation

Spring @Transactional defaults to REQUIRED propagation. With two distinct transaction managers, understand propagation per manager.

In the example:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void outer() {
    repository.save(...);
    publisher.inner();
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void inner() {
    kafkaTemplate.send(...);
}
~~~

If outer creates a DB transaction and inner creates a separate Kafka transaction, the two managers govern two distinct resources. The inner Kafka transaction commits when inner returns, while the DB remains open.

However, if a Kafka transaction is already active before calling inner, REQUIRED propagation may join the existing Kafka transaction. In that case, inner returning **does not mean** the Kafka transaction committed.

REQUIRES_NEW propagation can be considered in architectures that genuinely need an independent transaction, though it must not be applied blindly: active Kafka transactions, producer factories, resource bindings, transaction synchronization, and container offsets can all interact. Verify the APIs and test the specific commit order.

Do not use NESTED propagation assuming a shared savepoint exists between Kafka and a DB. Kafka transactions do not support a cross-system database savepoint.

## 22. Producer settings to configure

Kafka-first depends on the Kafka transaction committing durably before the DB commits.

Settings to understand:

| Property | Role |
|---|---|
| transaction-id-prefix / transactional.id | Enables transactional producer, supports coordinator and fencing |
| enable.idempotence | Prevents duplicates caused by certain producer-protocol retries |
| acks=all | Requires acknowledgement from replicas/ISR |
| delivery.timeout.ms | Limits time for the producer to complete a send |
| transaction.timeout.ms | Limits how long a transaction may remain open |
| request.timeout.ms | Time to wait for a request response |
| max.in.flight.requests.per.connection | Affects pipelined sends; must be compatible with idempotence |
| retry settings | Must be paired with timeouts; does not replace business idempotency |

If the transaction timeout is too long, Kafka outputs may stay invisible to read_committed downstream and hold resources. If too short, slow operations can cause the Kafka transaction to abort before logic completes.

Each active instance needs a safely managed transactional ID namespace. Reusing the same fixed transactional.id across multiple pods can cause producer fencing and continuous transaction failures.

## 23. Error handling by commit stage

For operations, distinguish which stage threw the exception:

### Stage A: before Kafka commit

Examples include validation failure, DB insert failure before publishing, or Kafka send failure. Typically both open transactions can roll back, provided the exception propagates to the outer interceptor.

### Stage B: Kafka commit fails or is uncertain

Do not assume the broker lacks the event. Collect eventId and transaction/error metadata, route the command to a reconciliation flow, or check idempotent state before retrying.

### Stage C: Kafka commit succeeded, DB commit failed

Kafka cannot be rolled back. This requires compensation, event-first reconciliation, or refactoring toward an outbox.

### Stage D: both commits succeeded, response to client was lost

The client may retry. Use commandId/idempotency key and unique business constraints to avoid creating unintended duplicate Orders or events.

A runbook must answer: who is responsible for investigating, when to retry, when to compensate, and which system holds authority over the final state.

## 24. Testing Kafka-first commit order

A unit test mocking KafkaTemplate and Repository is insufficient to prove commit order. Commits happen in transaction interceptors and resource managers, not merely at the two method call sites.

Use integration tests against a real database and real Kafka broker in a test environment (such as Testcontainers), and verify committed data.

### 24.1. Happy path

1. Invoke the outer service with a command carrying a fixed eventId.
2. Confirm the Kafka event appears on a read_committed consumer.
3. Confirm the database row committed.
4. Record transaction completion events to verify ordering.
5. Confirm the client receives success only after the database commit.

### 24.2. Kafka commit failure

1. Simulate a producer/coordinator or broker failure before Kafka commit.
2. Confirm the inner Kafka method does not complete normally.
3. Confirm the outer DB transaction rolls back per rollback rules.
4. Confirm no database row was committed.
5. Test uncertain Kafka commit outcomes using eventId.

### 24.3. Database commit failure after Kafka commit

This is the core test for Kafka-first:

1. Start the outer DB transaction, save the row without committing yet.
2. Call the inner Kafka transactional publisher and let Kafka commit succeed.
3. Deliberately fail the database commit after the inner method returns.
4. Confirm downstream read_committed sees the Kafka event.
5. Confirm the database has no corresponding committed row.
6. Confirm the system triggers an alert/reconciliation rather than failing silently.

In the test, trigger the failure specifically at **database commit time**, rather than throwing an exception mid-way through the outer method if doing so inadvertently prevents the inner Kafka transaction from committing.

### 24.4. Consumer reading before database commit

1. Hold the outer DB transaction open after the inner Kafka transaction has committed.
2. Have downstream read the event with a read_committed consumer.
3. Query the DB from another connection and verify the row is not visible yet.
4. Then let the outer DB commit succeed.
5. Confirm downstream retries/handles eventual consistency appropriately.

### 24.5. Duplicate command after response timeout

1. Send commandId X and let both commits succeed.
2. Simulate a lost response.
3. Resend the same commandId X.
4. Confirm no unintended duplicate side effects/events are created.
5. Confirm the eventId remains stable across attempts.

### 24.6. Container-initiated transaction

1. Create a transactional @KafkaListener with an inner DB transaction.
2. Observe DB committing before the container's Kafka commit under actual configuration.
3. Confirm an inner Kafka method does not prematurely close the container transaction if it only joins the current transaction.
4. Fail the Kafka commit and test DB idempotency on redelivery.
5. Do not apply conclusions from producer-initiated nested methods to listeners without verifying.

## 25. Observing commit order in production

Signals to monitor:

**Kafka transaction**

- Transaction commit/abort counts and failure rates.
- Transaction duration, timeouts, and producer fencing.
- Delivery timeouts and KafkaTemplate errors.
- EventId/correlationId on committed outputs.

**Database**

- Transaction commit/rollback counts.
- Deadlocks, constraint violations, and connection errors.
- Elapsed time from INSERT to DB commit.
- Count of transactions failing commit after Kafka publish.

**Consistency**

- Count of Kafka events without a corresponding DB row after a threshold duration.
- Count of DB rows without a Kafka event if the application also has DB-first paths.
- Count of compensation/reconciliation attempts.
- Count of duplicate commands rejected by the idempotency layer.
- Age of the oldest unreconciled incident.

For commit order, you can log safe lifecycle markers such as:

    commandId=cmd-123 stage=db_tx_open
    commandId=cmd-123 stage=kafka_tx_commit_success
    commandId=cmd-123 stage=db_tx_commit_success

If the database commit fails:

    commandId=cmd-123 stage=kafka_tx_commit_success
    commandId=cmd-123 stage=db_tx_commit_failed

Do not log Kafka credential secrets, payment details, or sensitive payloads. Stage logs can be lost, so reconciliation should rely on durable state and business identifiers rather than logs alone.

## 26. Common misconceptions

| Misconception | Reality |
|---|---|
| Calling KafkaTemplate.send before repository.save commits Kafka first | Method order differs from commit order |
| Having @Transactional makes DB and Kafka atomic | Two transaction managers do not automatically use XA |
| Kafka-first is always better than DB-first | It shifts the risk to orphan Kafka events |
| Kafka commits then DB rolls back will roll back Kafka | A committed Kafka transaction cannot be aborted retroactively |
| KafkaTemplate.send succeeding means Kafka transaction committed | Transaction commit is a separate boundary |
| Inner @Transactional always starts a new Kafka transaction | It may join an existing Kafka transaction |
| Nested annotations in the same bean always take effect | Self-invocation can bypass the Spring AOP proxy |
| read_committed guarantees the DB has committed | It only applies to Kafka transactions, not the database |
| Producer idempotence prevents duplicate business commands | Requires commandId/eventId and deduplication |
| Kafka-first solves all errors when a container consumes Kafka | Input offsets and container transactions add extra risks |
| Retrying after a Kafka timeout is always safe | Commit outcome may be uncertain |
| Changing commit order replaces an outbox | Outbox solves the failure window with a different model |

## 27. When should Kafka-first be considered?

Kafka-first may be considered when:

- Kafka events are the primary data source and the database is only a rebuildable projection.
- Downstream accepts eventual consistency and does not assume a DB row is committed upon seeing an event.
- A clear reconciliation or compensation mechanism exists.
- Every command has a stable ID and duplicates are handled idempotently.
- Operations have tested DB commit failures after Kafka commits.
- The business process treats events as intent or a compensable step, rather than a commitment of final DB state.

Do not choose Kafka-first merely because you think "Kafka is faster than the database." For services where the DB is the source of truth, events represent effective DB changes, and consumers need to query the DB immediately, a transactional outbox is usually easier to make reliable.

## 28. Principles to remember

- **Kafka-first commit order = Kafka commits first, database commits second.**
- Establish commit order via transaction boundaries, not the order of save/send calls.
- For producer-initiated flows, an outer DB @Transactional and inner Kafka @Transactional on **two separate Spring beans** is a commonly used pattern.
- The inner Kafka method must use the proper KafkaTransactionManager and KafkaTemplate/ProducerFactory.
- If the inner Kafka commit fails, the outer DB can roll back according to rollback rules.
- If the Kafka commit succeeds and the DB commit subsequently fails, the Kafka event remains: this failure window cannot be eliminated with nested transactions.
- Downstream read_committed only protects against aborted Kafka transactions, not pending DB commits.
- Container-initiated Kafka transactions have different boundaries from producer-initiated transactions; do not copy configurations mechanically.
- If the input Kafka offset commits before the DB side effect, there is a risk the record will not be redelivered automatically when the DB fails.
- Use stable eventId/commandId values, idempotency, and a reconciliation mechanism.
- If the DB is the source of truth, consider transactional outbox/inbox.
- Test Kafka success + DB commit failure as well as uncertain commit outcome scenarios.

Kafka-first is not an "exactly-once guarantee between Kafka and a database." It is a **commit ordering** choice with its own benefits and risks. A reliable design must explicitly name the Kafka-committed/DB-not-committed failure window, decide who owns recovery, and ensure business actions are neither duplicated nor lost when requests, listeners, or transactions are retried.
