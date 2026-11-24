# Nested @Transactional for commit order

A Spring Boot business operation often needs to **both update a database and publish a Kafka event**. For example, when confirming an order, the application updates its status in PostgreSQL and sends `OrderConfirmed` to the `orders.events` topic. These two operations can live in two local transactions managed by different transaction managers. Even though both execute in the same Java method, committing the database and committing Kafka **do not automatically become a single atomic operation**.

**Nested @Transactional for commit order** is a technique that places transactional methods inside one another, specifying the appropriate transaction manager for each resource, to control whether **the database commits before Kafka** or **Kafka commits before the database**. Choosing the order matters because after the first resource commits, the second resource can still fail.

In the **Kafka and databases** chapter of **Spring Kafka Reliability Operations**, the key takeaway is: nested transactional methods help control commit order; they **are not two-phase commit**, do not by themselves provide exactly-once semantics across a database and Kafka, and still require idempotency, an outbox, or reconciliation when data must not diverge.

## 1. One business operation, two commit points

Suppose a service has two side effects:

1. Change order 1001's status from `CREATED` to `CONFIRMED` in the database.
2. Publish an `OrderConfirmed(orderId=1001)` event to Kafka.

~~~mermaid
flowchart LR
    A["HTTP confirmOrder"] --> S["OrderService"]
    S --> D["PostgreSQL orders"]
    S --> K["Kafka orders.events"]
    D --> C1["DB COMMIT"]
    K --> C2["Kafka COMMIT"]
~~~

Without a shared distributed protocol committing both together, four states exist:

| Database | Kafka | Business outcome |
|---|---|---|
| Committed | Committed | Both DB and event reflect order confirmation |
| Committed | Uncommitted | DB changed, but downstream lacks the event |
| Uncommitted | Committed | Downstream receives an event without a committed DB change |
| Uncommitted | Uncommitted | Operation can be retried per policy |

The middle two states represent **dual-write inconsistency**. No ordering of two local commits eliminates all failure windows. Ordering only determines **which type of inconsistency can occur after the first commit**.

### 1.1 Failures are not just send exceptions

A `KafkaTemplate.send()` completing successfully only reflects one milestone in sending to Kafka. When the producer runs inside a transaction, **send acknowledgment differs from transaction commit**. A Kafka record can be broker-ACKed and still belong to a transaction that later aborts; a `read_committed` consumer will not treat the aborted record as valid.

Similarly, `repository.save()` or `EntityManager.flush()` succeeding does not mean the SQL transaction committed. The database commit can fail after flush due to deferred constraints, network issues, or commit-time errors.

Therefore, when speaking of "DB-first" or "Kafka-first," specify **actual commits**, not the call order of `save()` and `send()`.

## 2. Two independent transaction managers

Spring uses a transaction manager to start and finish a local transaction.

- **JpaTransactionManager** typically manages JPA/Hibernate database transactions.
- **DataSourceTransactionManager** typically manages JDBC database transactions.
- **KafkaTransactionManager** manages Kafka transactions through a transactional `ProducerFactory`.

Each annotation should explicitly declare the manager it uses:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void updateDatabase() {
    // ...
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void publishKafkaEvent() {
    // ...
}
~~~

In an application with both DB and Kafka managers, writing plain `@Transactional` can resolve to an unexpected default manager. To keep commit order readable and testable, specify the manager name explicitly on both outer and inner methods.

### 2.1 "Nested" means nested calls, not Propagation.NESTED

In this lesson, **nested @Transactional** means method A with a DB transaction calls method B with a Kafka transaction through a Spring proxy. They are **two distinct local transactions**.

It does **not** mean:

~~~java
@Transactional(propagation = Propagation.NESTED)
~~~

`Propagation.NESTED` may use a database savepoint when supported by the manager. A database savepoint does not create a Kafka subtransaction and does not make Kafka and SQL commits atomic.

Likewise, using `Propagation.REQUIRES_NEW` on one manager does not turn two resources into a distributed transaction. `REQUIRES_NEW` changes lifecycle/suspension of its respective transaction; it does not provide two-phase commit across Kafka and a database.

## 3. Defining DB-first and Kafka-first precisely

| Strategy | First commit | Second commit | Critical failure window |
|---|---|---|---|
| **DB-first** | Database | Kafka | DB committed; Kafka commit can fail |
| **Kafka-first** | Kafka | Database | Kafka committed; DB commit can fail |

Two common structural patterns exist:

**DB-first via Spring transaction synchronization:**

~~~text
Outer @Transactional(dbTransactionManager)
    UPDATE database
    KafkaTemplate.send() inside synchronized Kafka transaction
Outer method completes
    DB COMMIT
    Kafka COMMIT (synchronized secondary transaction)
~~~

**Kafka-first via nested transactional methods:**

~~~text
Outer @Transactional(dbTransactionManager)
    UPDATE database
    Inner @Transactional(kafkaTransactionManager)
        KafkaTemplate.send()
    Inner method completes
        Kafka COMMIT
Outer method completes
    DB COMMIT
~~~

Common pitfall: **Kafka-first does not mean the Kafka transaction must be the outermost transaction**. If the Kafka transaction is outer and the DB transaction is inner, the DB transaction can commit before the outer Kafka transaction finishes—resulting in DB-first again.

## 4. Prerequisite: Kafka ProducerFactory must be transaction-capable

`KafkaTemplate` requires a transactional producer to participate in a Kafka transaction or synchronize with a Spring database transaction.

In Spring Boot, configuration typically includes:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      transaction-id-prefix: orders-tx-instance-01-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        acks: all
        enable.idempotence: true
        transaction.timeout.ms: 60000
~~~

This is only **one illustrative instance**. In multi-pod production, the transaction ID prefix must be unique across concurrently active `ProducerFactory` instances. Do not reuse the same `instance-01` value across all pods, because transactional producers sharing a `transactional.id` can fence each other.

A startup guard:

~~~java
@Component
public class TransactionalProducerGuard {

    public TransactionalProducerGuard(
            ProducerFactory<String, OrderConfirmed> factory) {

        if (!factory.transactionCapable()) {
            throw new IllegalStateException(
                "Order publisher requires transactional ProducerFactory"
            );
        }
    }
}
~~~

Make sure you check **the actual factory used by KafkaTemplate**. An application may have both transactional and non-transactional factories; checking the wrong factory proves nothing.

### 4.1 KafkaTransactionManager and KafkaTemplate sharing the same factory

Example bean declarations:

~~~java
@Bean
KafkaTemplate<String, OrderConfirmed> orderKafkaTemplate(
        ProducerFactory<String, OrderConfirmed> orderProducerFactory) {
    return new KafkaTemplate<>(orderProducerFactory);
}

@Bean
KafkaTransactionManager<String, OrderConfirmed> kafkaTransactionManager(
        ProducerFactory<String, OrderConfirmed> orderProducerFactory) {
    return new KafkaTransactionManager<>(orderProducerFactory);
}
~~~

`KafkaTemplate` and `KafkaTransactionManager` share the same `ProducerFactory` instance. With Spring Boot auto-configuration, Boot can wire equivalent beans when enabled via properties and not overridden by custom beans; verify against your deployed version.

**`transactionCapable()=true` only means the factory can create transactional producers**; it does not mean a transaction has already started or that consumer offsets are included in the transaction.

## 5. DB-first with database @Transactional and Kafka synchronization

Spring Kafka supports synchronizing a Kafka transaction with a Spring-managed database transaction. When the DB transaction is primary and `KafkaTemplate` uses a transactional `ProducerFactory`, the Kafka transaction can synchronize with the outer transaction via the framework mechanism.

Example:

~~~java
@Service
public class DbFirstOrderService {

    private final OrderRepository repository;
    private final KafkaTemplate<String, OrderConfirmed> kafkaTemplate;

    public DbFirstOrderService(
            OrderRepository repository,
            KafkaTemplate<String, OrderConfirmed> kafkaTemplate) {
        this.repository = repository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId) {

        Order order = repository.findById(orderId)
            .orElseThrow();

        order.confirm();

        kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId)
        );
    }
}
~~~

Assume the DB transaction manager matches the repository (`JpaTransactionManager` for JPA), `KafkaTemplate` is transactional, Spring transaction synchronization is active, and no other outer Kafka transaction exists. Then:

~~~mermaid
sequenceDiagram
    participant S as DbFirstOrderService
    participant DB as Database
    participant KT as KafkaTemplate
    participant K as Kafka broker
    S->>DB: BEGIN DB transaction
    S->>DB: UPDATE orders
    S->>KT: send(OrderConfirmed)
    KT->>K: Produce record in Kafka transaction
    S->>DB: COMMIT DB
    S->>K: COMMIT Kafka transaction
~~~

### 5.1 Why is this DB-first?

Even though `KafkaTemplate.send()` is called before the DB commit, the Kafka transaction has not ended yet. Spring synchronization coordinates completing the Kafka transaction after the primary transaction (DB). **Send** order is not **commit** order.

Example timeline:

~~~text
t0  BEGIN DB
t1  UPDATE orders
t2  Kafka send enlisted in Kafka transaction
t3  Java method completes normally
t4  DB COMMIT                            <-- DB is durable
t5  Kafka COMMIT                         <-- event committed
~~~

### 5.2 Failure after DB commit

If `t4` succeeds and `t5` fails:

~~~text
orders.status = CONFIRMED         [DB COMMITTED]
OrderConfirmed event             [KAFKA COMMIT FAILED]
~~~

This is the major risk of DB-first. The database cannot roll back a completed transaction simply because the subsequent Kafka commit failed. In modern Spring Kafka releases, commit errors from the synchronized secondary transaction can be propagated to the caller; check the exact semantics of the version you run.

An HTTP 500 after an exception **does not prove the DB rolled back**. If the client retries the entire command, it could create duplicate business effects or events, or skip the missing event because the database is already in `CONFIRMED` state.

### 5.3 When DB-first is appropriate

DB-first can be appropriate if:

- The database is the source of truth.
- Events can be reconstructed via reliable reconciliation.
- There is no strict requirement that the event be published immediately.
- Requests carry an idempotency key and the system distinguishes "DB succeeded, event pending."
- Monitoring detects operations missing Kafka events.

If an event **must never be lost** and there is no durable publication intent, consider transactional outbox rather than synchronization alone.

## 6. Kafka-first using nested @Transactional

To commit Kafka before the DB commits, have an **outer DB `@Transactional`** call an **inner Kafka `@Transactional`** on a different Spring bean. When the inner method finishes, `KafkaTransactionManager` commits. Then when the outer method finishes, the DB commits.

~~~mermaid
sequenceDiagram
    participant API as API
    participant OUT as Outer DB service
    participant IN as Inner Kafka publisher
    participant DB as Database
    participant K as Kafka broker
    API->>OUT: confirm(orderId)
    OUT->>DB: BEGIN DB transaction
    OUT->>DB: UPDATE order
    OUT->>IN: publishConfirmed() via Spring proxy
    IN->>K: BEGIN Kafka transaction
    IN->>K: SEND OrderConfirmed
    IN->>K: COMMIT Kafka transaction
    IN-->>OUT: Return
    OUT->>DB: COMMIT DB
    OUT-->>API: Return
~~~

### 6.1 Outer DB service

~~~java
@Service
public class KafkaFirstOrderService {

    private final OrderRepository repository;
    private final TransactionalOrderPublisher publisher;

    public KafkaFirstOrderService(
            OrderRepository repository,
            TransactionalOrderPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId) {

        Order order = repository.findById(orderId)
            .orElseThrow();

        order.confirm();

        // Goes through Spring proxy on another bean:
        publisher.publishConfirmed(orderId);

        // DB transaction commits only after this method finishes.
    }
}
~~~

### 6.2 Inner Kafka publisher

~~~java
@Service
public class TransactionalOrderPublisher {

    private final KafkaTemplate<String, OrderConfirmed> kafkaTemplate;

    public TransactionalOrderPublisher(
            KafkaTemplate<String, OrderConfirmed> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishConfirmed(String orderId) {

        kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId)
        );
    }
}
~~~

With transaction managers and Spring proxies wired properly, the inner Kafka transaction commits when `publishConfirmed()` ends. The outer DB transaction stays open until `confirm()` ends.

### 6.3 Kafka-first timeline

~~~text
t0  BEGIN DB
t1  UPDATE orders (uncommitted)
t2  BEGIN Kafka transaction from inner method
t3  Kafka send(OrderConfirmed)
t4  Kafka COMMIT                            <-- event committed
t5  inner publishConfirmed() return
t6  DB COMMIT                               <-- DB committed
~~~

If the Kafka commit fails at `t4` and the exception propagates, the outer DB transaction can roll back per rollback rules. However, if the Kafka commit succeeds and then the DB commit fails at `t6`, the event can still exist in Kafka.

### 6.4 Kafka-first has a serious race condition

Right after `t4` and before `t6`, a `read_committed` consumer can see `OrderConfirmed` and query the database. Under proper isolation, the consumer still sees the order status as `CREATED` because the DB transaction has not committed yet.

If the DB eventually rolls back, the consumer has received an event describing a change that **never became committed DB state**.

Kafka-first should therefore not be chosen just to "publish early." It fits architectures that can tolerate or compensate for events committed ahead of the database; if the database is the source of truth and consumers depend on DB state, DB-first or outbox is usually easier to operate.

### 6.5 Do not send to Kafka before opening the inner transaction

If the outer DB method calls `KafkaTemplate.send()` before calling the inner Kafka publisher, the template may already have synchronized a Kafka transaction with the outer DB transaction. Then the intended boundary becomes unclear.

In a Kafka-first design, group the Kafka sends that must commit early inside **the dedicated inner Kafka transactional method** and verify the transaction outcome in tests.

## 7. Swapping outer/inner does not mean swapping commit order

A common mistake:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void outer() {
    databaseService.updateInTransaction();
    kafkaTemplate.send(...);
}
~~~

If `databaseService.updateInTransaction()` uses a DB transaction and finishes before the outer Kafka method, **the DB commit can happen before the Kafka commit**. That is still DB-first even though the Kafka transaction opened first.

Similarly, an `@Transactional` without an explicit manager does not prove which manager is used when the application has multiple transaction managers.

Remember the rule:

**The inner method's commit usually happens before the outer method's commit, provided the two methods actually open two independent local transactions as designed.**

Do not infer commit order from the order annotations appear in source code. To be certain, identify which transaction is opened by a proxy or container, its manager, and when interceptors complete.

## 8. Spring AOP proxies and self-invocation

Nested `@Transactional` only works as intended when the inner method is handled by the Spring transaction interceptor.

**Unreliable** example:

~~~java
@Service
public class OneBeanOrderService {

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId) {
        repository.updateStatus(orderId, "CONFIRMED");

        // Self-invocation:
        publishConfirmed(orderId);
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishConfirmed(String orderId) {
        kafkaTemplate.send("orders.events", orderId, ...);
    }
}
~~~

The call from `confirm()` to `publishConfirmed()` goes directly within the same object rather than through the Spring proxy in default proxy mode. As a result, the inner method's `@Transactional` annotation may **not be applied**. `KafkaTemplate` may simply synchronize with the outer DB transaction, turning the order into DB-first, or throw an exception depending on configuration.

### 8.1 Safer approach

~~~text
KafkaFirstOrderService.confirm()
    @Transactional(dbTransactionManager)
       |
       v via Spring proxy
TransactionalOrderPublisher.publishConfirmed()
    @Transactional(kafkaTransactionManager)
       |
       v
KafkaTemplate
~~~

Split into two separate Spring beans so each proxy interceptor can open and commit its resource transaction at the intended boundary.

### 8.2 Other cases that can break transaction boundaries

- `private` or `final` methods are not proxied under default proxy mechanisms.
- Objects instantiated with `new` rather than managed by Spring.
- One method in a bean calling another via `this`.
- `@Async` or executors moving Kafka work to another thread that does not inherit the thread-bound transaction context.
- Annotation placed on a code path not invoked through the proxy.
- Application already has an outer Kafka listener container transaction, causing an inner `@Transactional` to join the existing Kafka transaction.

Reading source code with two annotations is not enough. **You need integration tests to confirm commit order.**

## 9. @Transactional rollback rules and exception propagation

Spring `@Transactional` has a rollback policy. By default in many imperative configurations, `RuntimeException` and `Error` trigger rollback, whereas checked exceptions may require explicit `rollbackFor`.

Consider Kafka-first:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void confirm(String orderId) {
    repository.updateStatus(orderId, "CONFIRMED");
    publisher.publishConfirmed(orderId);
}
~~~

If the Kafka transaction fails and the exception propagates out of `confirm()`, the outer database transaction can roll back. But if code catches the exception, logs it, and returns normally:

~~~java
try {
    publisher.publishConfirmed(orderId);
}
catch (Exception ex) {
    log.error("Kafka publish failed", ex);
    // Normal return: outer DB transaction may commit.
}
~~~

The DB commit can still occur even though Kafka failed. This may be intentional when an outbox/reconciliation exists, but must never happen accidentally by swallowing errors.

### 9.1 Commit failure after the first resource cannot be rolled back retroactively

DB-first:

~~~text
DB COMMIT [succeeded]
Kafka COMMIT [failed]
~~~

Kafka-first:

~~~text
Kafka COMMIT [succeeded]
DB COMMIT [failed]
~~~

An exception thrown during the second commit does not automatically roll back the first commit. You need business compensation or recovery, not a simple Java method rollback.

### 9.2 Commit outcome may be unknown

If a Kafka commit request reached the broker but the client never received the response due to a timeout, the application cannot immediately conclude whether the commit was accepted. Likewise, database commits can encounter network failures leaving the caller unsure of the outcome.

Never infer "it threw an exception, so it definitely did not commit." Use operation/event IDs, durable state inspection, idempotency, and reconciliation before retrying the entire operation.

## 10. KafkaTemplate.send() and transaction commit are two separate steps

In modern Spring Kafka, `KafkaTemplate.send()` typically returns a `CompletableFuture`; older versions may use a different future API. Future completion does not mean the entire Kafka transaction has committed.

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishConfirmed(String orderId) {

    CompletableFuture<SendResult<String, OrderConfirmed>> future =
        kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId)
        );

    // Send result can be observed, but the commit will
    // be handled by KafkaTransactionManager at the transaction boundary.
}
~~~

Distinguish four milestones:

1. `KafkaTemplate.send()` is called.
2. Producer receives send result/ACK or exception.
3. Kafka transaction commits or aborts.
4. `read_committed` consumer can read the committed record.

If business logic needs to detect send failures inside the method, await the future with a sensible timeout. Yet waiting extends transaction lifetime, and even if the send future succeeds, the transaction commit can still fail.

**Do not offload sends to `CompletableFuture.runAsync()` inside an inner Kafka transactional method and return immediately** without designing transaction context propagation and failure handling. Spring transactions are usually thread-bound; work on another executor thread can run outside the intended transaction.

## 11. Commit order decision table

| Business condition | DB-first | Kafka-first | Notes |
|---|---|---|---|
| DB is source of truth | Usually easier to reason about | Risk of event ahead of DB state | Still need handling for missing events |
| Kafka is source of truth, DB rebuildable | Possible | Worth considering | Needs well-designed event-first/replay |
| Events must never be missing after DB commit | Insufficient alone | Does not solve it | Outbox is a better fit |
| Consumer must query DB right on seeing event | Usually safer for visibility | Has race condition | Does not guarantee atomic dual write |
| Can compensate emitted event when DB rolls back | Depends | Acceptable | Needs compensation protocol |
| Want simple synchronous API | Possible | Possible | Both still have a failure window |
| Require exactly-once across SQL and Kafka | No | No | Needs different architecture or eventual consistency |

Document explicitly in the design doc: which transaction is primary, which is secondary, and what the system does if the second commit fails.

## 12. Nested transactions differ from transactional outbox

**Transactional outbox** is usually suitable when the database is the source of truth and Kafka events must never be missing after a DB update.

~~~mermaid
flowchart TD
    S["Business service"] --> T["One DB transaction"]
    T --> D["UPDATE orders"]
    T --> O["INSERT outbox_event"]
    D --> C["DB COMMIT"]
    O --> C
    C --> R["Outbox relay / CDC"]
    R --> K["Kafka orders.events"]
    K --> P["Downstream consumers"]
~~~

Inside one DB transaction:

1. Update `orders`.
2. Write `outbox_event` containing the event ID and payload/contract.
3. Commit once in the database.

The outbox relay publishes the Kafka event after commit. If Kafka is unavailable, the outbox row remains for retry. If the relay publishes to Kafka and crashes before marking the row published, it may publish a duplicate; consumers need idempotency.

Conceptual example:

~~~java
@Service
public class OutboxOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId, String operationId) {

        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();

        outbox.save(
            OutboxEvent.orderConfirmed(
                operationId,
                orderId
            )
        );
    }
}
~~~

Outbox solves **durable publication intent**: DB state and publish intent are written atomically in the same database. It does not promise each event has only one physical Kafka record; consumers must deduplicate.

### 12.1 When is nested @Transactional still used?

Nested `@Transactional` can be useful when:

- The primary goal is controlling commit order.
- Inconsistencies have a clear reconciliation mechanism.
- Eventually consistent events are acceptable.
- The system does not require a durable outbox for this flow.
- You want to govern a transactional Kafka publish block within the same business operation.

However, if the rule is "once the DB has confirmed an order, the event must be published even during a Kafka outage," outbox is usually far more reliable than hoping the second commit always succeeds.

## 13. Request idempotency and consumer inbox

Because local transactions can commit asynchronously or asymmetrically, both clients and downstream consumers must be protected from duplicates.

### 13.1 Request ID

The order confirmation API should carry a stable `operationId`/`requestId`. When a client retries due to an HTTP timeout or 500, the service checks whether the operation already executed.

Do not generate a fresh event ID on each retry and treat it as a new operation when business rules require a single confirmation.

### 13.2 Event ID

An `OrderConfirmed` event has a unique `eventId`. If the outbox relay or Kafka producer republishes, consumers can detect duplicates using `eventId`.

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Inside a consumer DB transaction, record the processed event alongside the business effect. Relying solely on `SELECT exists` followed by a separate `INSERT` without a unique constraint suffers race conditions when two workers process concurrently.

### 13.3 Kafka exactly-once does not cover DB side effects

In consume-transform-produce, Kafka can atomically commit output records and consumed offsets when the transactional container is configured properly. Yet writing to a database inside the listener remains a separate transaction. If the database commits and then the Kafka transaction aborts, the input record can be redelivered, repeating the database side effect.

Nested `@Transactional` does not replace inbox/deduplication on consumers.

## 14. Special caution for @KafkaListener transactional containers

An example where an outer DB service calls an inner Kafka publisher **must not be applied mechanically to a `@KafkaListener` running inside a Kafka container transaction**.

With a transactional listener container, the Kafka transaction can start **before the listener method is called**:

~~~text
Kafka listener container opens Kafka transaction
    listener invoked
        DB transactional method begins
        DB COMMIT
    listener returns
    container sends consumed offsets to Kafka transaction
Kafka COMMIT
~~~

This is typically DB-first in commit order, because the inner DB transaction completes before the container's Kafka transaction.

When an active outer Kafka transaction already exists, an inner `@Transactional("kafkaTransactionManager")` method may join the existing transaction instead of creating a new Kafka transaction that commits immediately. Hence, do not conclude a call graph is Kafka-first merely because you extracted an inner Kafka method.

Distinguish clearly:

- **Producer service workflow:** outer DB transaction and inner Kafka transaction as in the Kafka-first example.
- **Consumer container workflow:** container may open the Kafka transaction before the listener, committing Kafka outputs + consumed offsets when the listener succeeds.
- **Database inside a listener:** still a local DB transaction, with its own failure window and idempotency requirements.

With transactional listeners, exceptions usually abort the Kafka transaction; Spring Kafka offers rollback/recovery mechanisms such as `AfterRollbackProcessor` depending on version. Do not apply the non-transactional `DefaultErrorHandler` model directly to reason about the entire transactional flow.

## 15. Producer fencing, timeouts, and lifecycle

Nested transactions can fail due to Kafka producer configuration rather than DB code.

### 15.1 Duplicate transactionIdPrefix across pods

~~~text
Pod A: transactionIdPrefix = orders-tx-common-
Pod B: transactionIdPrefix = orders-tx-common-
~~~

If factories generate the same `transactional.id`, one producer can fence the other. `ProducerFencedException` can cause the Kafka commit to fail. Assign a unique prefix per active instance and manage producer lifecycles properly.

### 15.2 Long-running transactions

If an inner Kafka method makes slow external network requests or waits too long, the transaction can exceed `transaction.timeout.ms`. The transaction coordinator can abort it.

Do not use a Kafka transaction to span a long workflow. Wrap only the Kafka operations that must commit/abort together, bound processing time, and set clear timeouts.

### 15.3 Duplicates from retries after unknown commits

When a remote commit returns a network error, the service must treat the outcome as requiring reconciliation. Do not retry infinitely with a fenced or fatal producer, and do not automatically issue new business event IDs on every retry.

## 16. Monitoring commit order in production

Track independently:

- DB commit / rollback outcomes.
- Kafka send ACKs.
- Kafka transaction commit / abort outcomes.
- Transaction synchronization errors.
- Operation ID and event ID.
- Retry/reconciliation state.
- Outbox pending count and oldest pending age, if using an outbox.
- Duplicate detections at consumers.
- Kafka producer fencing and transaction timeouts.

Example contextual log:

~~~text
operationId=confirm-1001
eventId=evt-1001
strategy=DB_FIRST
dbCommit=SUCCESS
kafkaCommit=FAILED
action=RECONCILIATION_REQUIRED
~~~

With Kafka-first:

~~~text
operationId=confirm-1002
eventId=evt-1002
strategy=KAFKA_FIRST
kafkaCommit=SUCCESS
dbCommit=FAILED
action=COMPENSATION_REQUIRED
~~~

Do not log "publish success" as soon as `send()` returns and treat it as a Kafka transaction commit.

### 16.1 How to investigate inconsistencies

1. Identify `operationId`/`eventId`.
2. Read the committed DB state.
3. Check whether the event actually committed in Kafka by topic/key/eventId.
4. Check the active strategy and method transaction managers.
5. Verify method invocations go through Spring proxies.
6. Distinguish send failures, Kafka commit failures, and DB commit failures.
7. Check transaction ID prefixes, broker health, and timeouts.
8. Cross-check downstream side effects.
9. Decide whether to publish the missing event, emit compensation, or run reconciliation.
10. Retry operations only under a clear idempotency/recovery policy.

## 17. Integration tests proving commit order

Mocking `KafkaTemplate` or repositories cannot prove commit order. Use a real database (PostgreSQL Testcontainers) and an integration Kafka broker to test the two local transactions.

### 17.1 DB-first happy path

- Invoke DB-first confirm with a new operation ID.
- Verify the DB order status committed.
- Use a `read_committed` Kafka consumer to read `OrderConfirmed`.
- Verify event ID and order ID match the DB.
- Capture transaction lifecycle logs/traces to confirm DB commits before Kafka commits.

### 17.2 Kafka-first happy path

- Invoke the outer DB service.
- Inner Kafka publisher commits successfully.
- Use a barrier/test latch to hold the outer DB transaction open.
- Use a `read_committed` consumer to receive the Kafka event.
- Query the DB from another connection; depending on isolation level, the uncommitted state is not yet visible.
- Release the DB commit and verify final state.

This test proves the event can become visible **before** the DB commits under Kafka-first.

### 17.3 Fault injection in the right failure window

DB-first tests must let **the DB commit succeed** and then simulate **a Kafka commit failure**. Throwing an exception inside the method before commit does not test that failure window.

Kafka-first tests must let **the Kafka commit succeed** and then simulate **a DB commit failure**. Throwing an exception before calling the inner publisher also fails to test that window.

Failure-injection hooks and proxies must be designed carefully so they do not misrepresent transaction order.

### 17.4 Testing self-invocation

- Call the inner annotated method within the same bean.
- Observe the proxy does not intercept self-invocation in default configuration.
- Extract the inner method to another bean.
- Re-run and verify transaction boundaries/commit order match expectations.

### 17.5 Testing retries and outbox

- Client retries the same `operationId` after an error response.
- Verify the database creates no duplicate business effects.
- Verify the outbox event persists during a Kafka outage.
- Have the relay republish and crash before marking published.
- Verify consumer inbox/deduplication handles duplicates safely.

## 18. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Expected Kafka-first, still DB-first | Self-invocation or inner transaction did not open | Split Spring beans and verify proxies |
| KafkaTemplate has no transaction | ProducerFactory is not transaction-capable | Configure `transactionIdPrefix` and wiring |
| Event appears before DB update | Kafka-first committed before DB | Evaluate race condition and downstream contract |
| DB changed, event missing | Kafka commit failed after DB commit | Outbox/reconciliation |
| Event exists, DB rolled back | DB commit failed after Kafka commit | Compensation/reconciliation |
| Two pods fencing each other | Duplicate transactional ID prefix | Unique identity per active instance |
| `@Transactional` runs with wrong manager | Default manager is not the expected DB/Kafka one | Explicit `transactionManager` name |
| Kafka send ACKed, invisible to `read_committed` | Transaction uncommitted or aborted | Check transaction outcome, LSO |
| Repeated DB updates after retries | Missing request/event idempotency | Unique constraints, inbox |
| Nested Kafka method does not commit immediately | Outer Kafka transaction already active | Identify container transaction boundary |

## 19. Misconceptions to avoid

**"Two `@Transactional` methods equal one distributed transaction."** No. They are typically two local transactions.

**"Nested `@Transactional` means `Propagation.NESTED`."** Not in this context; nested here means DB and Kafka methods calling one another.

**"If Kafka is the outer transaction, Kafka commits first."** Not necessarily; an inner DB transaction can commit before the outer Kafka transaction.

**"Calling `send()` first means Kafka commits first."** No. Send order differs from commit order.

**"Kafka-first is always better because events arrive early."** No. Consumers can read events before the DB commits or see events even if the DB rolls back.

**"DB-first guarantees events are not lost."** No. A Kafka commit after DB commit can fail.

**"An exception rolls back the first commit."** No. A completed commit is not reversed just because a later commit fails.

**"`REQUIRES_NEW` creates 2PC."** No.

**"Calling an inner `@Transactional` method in the same bean still opens a new transaction."** Do not assume this in Spring's default proxy mode.

**"Kafka EOS guarantees exactly-once DB side effects."** No. Kafka EOS covers Kafka outputs + consumed offsets; the DB needs idempotency/inbox.

**"Outbox guarantees zero duplicates in Kafka."** No. Outbox guarantees durable intent; relays and consumers still need deduplication.

## 20. Implementation checklist

**Transaction managers and code**

- [ ] DB and Kafka transaction managers have explicit names.
- [ ] The right `ProducerFactory` returns `transactionCapable()=true`.
- [ ] `KafkaTemplate` uses that `ProducerFactory`.
- [ ] DB-first or Kafka-first strategy is explicitly chosen.
- [ ] Inner Kafka method is invoked through a Spring proxy.
- [ ] No unintended self-invocation, async thread handoff, or container transaction interference.
- [ ] Nested methods are not confused with `Propagation.NESTED`.

**Failure handling**

- [ ] Runbook exists for DB commit succeeding followed by Kafka commit failure.
- [ ] Runbook exists for Kafka commit succeeding followed by DB commit failure.
- [ ] Procedure exists to resolve unknown outcomes after timeouts.
- [ ] Exceptions are not swallowed causing unintended outer transaction commits.
- [ ] Fixed `operationId`/`eventId` preserved across retries.
- [ ] Outbox or reconciliation exists when events must not be lost.
- [ ] Consumers have idempotency/inbox for duplicates.

**Verification and observability**

- [ ] Tested with a real DB and real Kafka.
- [ ] Commit order proven using transaction events, not just send calls.
- [ ] Tested the exact failure window between the two commits.
- [ ] Tested self-invocation and manager selection.
- [ ] Metrics exist for DB commits, Kafka commits/aborts, and producer fencing.
- [ ] Alerts exist for outbox backlog/inconsistencies.
- [ ] Reviewed `@KafkaListener` transactional container behavior separately if using listeners.

## 21. Conclusion

**Nested `@Transactional` for commit order** is a way to control **two local transaction boundaries**, not a distributed transaction. With Spring Kafka, using the DB transaction as primary with `KafkaTemplate` transaction synchronization typically yields **DB-first**. To achieve **Kafka-first**, an outer DB `@Transactional` can call an inner Kafka `@Transactional` through a Spring proxy, so Kafka commits when the inner method ends and the DB commits afterward.

Whichever order you choose, a **failure window remains between the two commits**. DB-first can leave committed database state with a missing Kafka event; Kafka-first can produce a committed event while the database is uncommitted or rolled back. Therefore, choose based on business invariants, measure actual commit outcomes, and design idempotency, reconciliation, or a transactional outbox whenever data must neither be lost nor diverge.

