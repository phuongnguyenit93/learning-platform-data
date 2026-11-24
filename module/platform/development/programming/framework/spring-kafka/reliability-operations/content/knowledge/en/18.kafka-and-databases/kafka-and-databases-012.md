# Avoiding Reliance on ChainedKafkaTransactionManager

In a Spring Kafka service, the requirement to "save to the database and emit a Kafka event in the same business operation" is very common. For instance, an order creation API inserts a row into the `orders` table and publishes `OrderCreated` for other services to process. The problem is that **PostgreSQL and Kafka have two independent commit mechanisms**. If the process crashes right between the two operations, one side may have persisted data while the other has not finished.

`ChainedKafkaTransactionManager` used to be employed to coordinate multiple local transaction managers in sequence. However, it **does not provide XA/two-phase commit** for Kafka and a database. This class was **deprecated in Spring Kafka 2.7**. Therefore, new applications should avoid depending on it, and legacy applications should actively choose a replacement matching their requirements: **Spring transaction synchronization** if ordered commits with error-compensation capability are acceptable, or **transactional outbox/inbox** if high reliability against crashes and disconnects is required.

This is an architectural decision, not merely changing a Java import. The goal of this lesson is to understand transaction boundaries, possible failure points, how to use Spring Kafka without a chained manager, and operational models suited to different data criticality levels.

## 1. Why is writing to a database and Kafka a dual-write problem?

A seemingly simple business flow:

```text
POST /orders
     |
     v
OrderService.create()
     |
     +----> PostgreSQL: INSERT INTO orders (...)
     |
     +----> Kafka: publish OrderCreated
     |
     v
HTTP 201 Created
```

A database transaction manages atomicity of SQL statements within the database scope. A Kafka transaction manages committing records sent by a transactional producer and, where applicable, Kafka consumer offsets. The two resources have separate logs, coordinators, networks, and commit points.

| Resource | What does the transaction protect? | Typical Spring component |
|---|---|---|
| PostgreSQL | Changes to tables within the same database transaction. | `DataSourceTransactionManager` / `JdbcTransactionManager`. |
| Kafka | Output records and optionally Kafka consumer offsets in the same Kafka transaction. | `KafkaTransactionManager`. |

### Failure window when committing the database first

```text
Database COMMIT succeeds
          |
          X process crash / Kafka commit fails
          |
Kafka event commit not confirmed
```

The order is already in the database, yet downstream may never receive the event without a durable record for republishing.

### Failure window when committing Kafka first

```text
Kafka COMMIT succeeds
          |
          X process crash / Database commit fails
          |
Database has not confirmed the order
```

Downstream consumers may read an event about an order that does not exist in the database. **Swapping commit order only swaps the type of risk**; it does not merge the two resources into one atomic transaction.

## 2. What did ChainedKafkaTransactionManager do?

`ChainedKafkaTransactionManager` chained multiple Spring `PlatformTransactionManager` instances via local transaction coordination. Its design started resource transactions and committed/rolled them back in a defined order.

Illustrative legacy configuration example:

```java
// Legacy: illustrative old code, not recommended for new projects.
ChainedKafkaTransactionManager<String, String> manager =
        new ChainedKafkaTransactionManager<>(
                dataSourceTransactionManager,
                kafkaTransactionManager);
```

This is not a transaction coordinator guaranteeing "either both commit or both roll back" under every failure condition. If the first resource's transaction commits successfully and the second resource's commit fails, the manager **cannot undo the first commit**.

Therefore, never draw the following conclusions:

- "Having one `@Transactional` means both Kafka and SQL commit atomically."
- "A Kafka transaction failure definitely rolls back PostgreSQL, even after the DB committed."
- "A chained manager provides exactly-once across both the database and Kafka."
- "Calling `commit()` sequentially in a wrapper solves the distributed transaction problem."

Deprecation since Spring Kafka 2.7 is a signal to move toward mechanisms with explicit contracts. Simply removing `ChainedKafkaTransactionManager` from source code is not enough to declare a migration successful; you must also design handling for **partial commits**.

## 3. Three alternatives to distinguish

| Option | Purpose | Limitation |
|---|---|---|
| Database transaction + Kafka synchronization | Write to DB and publish to Kafka in one business method with a clear commit order. | Commits across the two resources remain non-atomic; DB can commit then Kafka can fail. |
| Two nested `@Transactional` with two transaction managers | Intentionally reverse commit order, e.g., Kafka before DB. | Failure window still exists; event can exist before database state. |
| Transactional outbox + inbox/idempotency | Persist DB state and publish intent in **one DB transaction**, then retry publishing until it succeeds. | Typically at-least-once; requires deduplication, worker/CDC, and monitoring. |

When only reading Kafka inputs and producing Kafka outputs, a single Kafka transaction can include **outputs and consumer offsets** to achieve Kafka-to-Kafka exactly-once guarantees. However, adding a database as a second resource does not pull SQL into the Kafka transaction's atomic commit.

## 4. DB-first approach using Spring transaction synchronization

Spring Kafka supports synchronizing a Kafka transaction with an open Spring transaction. A `@Transactional` service uses a **database transaction manager**, then calls `KafkaTemplate.send(...)` backed by a **transactional producer factory**. The Kafka transaction is synchronized to commit after the primary database transaction.

```text
@Transactional(DB)
        |
        v
Begin DB transaction
        |
        v
INSERT/UPDATE business data
        |
        v
KafkaTemplate.send(event)
        |
        v
DB COMMIT
        |
        v
Kafka COMMIT
```

Advantage: concise code that avoids the chained manager. Drawback: if the Kafka commit fails **after** the DB commit, the database has already changed while the event remains unconfirmed. Spring can report the error to the caller, yet cannot automatically roll back an already-committed DB transaction.

### Spring Boot configuration

```yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/orderdb
    username: order_app
    password: DB_SECRET_FROM_ENVIRONMENT
  kafka:
    bootstrap-servers: kafka:9092
    producer:
      transaction-id-prefix: UNIQUE_PREFIX_PER_INSTANCE
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
```

`DB_SECRET_FROM_ENVIRONMENT` and `UNIQUE_PREFIX_PER_INSTANCE` are illustrative placeholders that must be supplied via appropriate secrets and environment variables. **The transaction ID prefix must differ across concurrently running pods**; otherwise producers can fence one another due to sharing a `transactional.id`.

When an application has multiple transaction managers, distinguish them by bean name:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean("dataSourceTransactionManager")
    PlatformTransactionManager dataSourceTransactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean("kafkaTransactionManager")
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Key imports:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
```

This is an illustrative configuration example. If Spring Boot already auto-configures the appropriate transaction manager beans, do not create redundant beans. In a real project, confirm bean names, `ProducerFactory` types, and `KafkaTemplate` wiring; never let `@Transactional` accidentally pick the Kafka manager when a DB transaction is intended.

### Service using the DB transaction as primary

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderService(
            OrderRepository orderRepository,
            KafkaTemplate<String, String> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public Order createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.from(command));

        String eventJson = toJson(order);
        kafkaTemplate.send("orders.created", order.getId(), eventJson);

        return order;
    }
}
```

`Order`, `OrderRepository`, `CreateOrderCommand`, and `toJson(...)` are application-defined types. When Kafka transaction synchronization works properly, `KafkaTemplate` sends output inside a Kafka transaction synchronized with the DB transaction.

**`KafkaTemplate.send()` returning a future does not mean the Kafka transaction committed.** Awaiting the send future can catch publish errors before the DB commit, yet does not eliminate the risk of the Kafka commit failing after the DB commit. Never claim this model is atomic DB–Kafka.

## 5. Crash matrix for DB-first synchronization

| Failure point | Database | Kafka | Required action |
|---|---|---|---|
| Before DB commit | Can roll back changes. | Transaction can abort. | Caller retries with a stable request ID. |
| After DB commit, before Kafka commit | Committed. | Commit unconfirmed. | Reconciliation / outbox / controlled republish. |
| Kafka commit fails after DB commit | Committed. | May be uncommitted or outcome unknown to client. | Do not retry blindly; check event ID and producer state. |
| Both commits succeed | Committed. | Committed. | Flow completes normally. |

If an exception is thrown after the DB committed, retrying the entire method can create a second order. Therefore you need a **request idempotency key**, unique constraint, or reconciliation by business ID. Never infer from an HTTP 500 that the database definitely rolled back.

## 6. What if you want Kafka to commit before the database?

You can use two purposefully nested `@Transactional` methods with **different managers**. The outer method opens the DB transaction; a separate bean opens the Kafka transaction in the inner method. The Kafka transaction finishes before the outer method commits the DB.

```text
BEGIN database transaction (outer)
             |
             v
       INSERT order
             |
             v
 BEGIN Kafka transaction (inner)
             |
             v
        Kafka send
             |
             v
    COMMIT Kafka transaction
             |
             v
    COMMIT database transaction
```

Example extracting a separate publisher bean:

```java
@Service
public class OrderKafkaPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderKafkaPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.created", orderId, payload);
    }
}
```

```java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final OrderKafkaPublisher publisher;

    public OrderCommandService(
            OrderRepository orders,
            OrderKafkaPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public Order create(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));
        publisher.publish(order.getId(), toJson(order));
        return order;
    }
}
```

Separating into **another bean** is crucial in Spring proxy-based transaction management: calling an `@Transactional` method via `this.method()` in the same bean normally **bypasses the proxy**, so the called method's transaction annotation is not applied.

**Kafka-first is no stronger in atomicity than DB-first.** If Kafka commits while the database commit fails, consumers may receive an event for an entity that does not exist in the DB. If downstream expects to query the DB immediately upon receiving the event, this can cause business errors. Choose this order only when the system handles eventual consistency or appropriate compensation.

## 7. Do not confuse synchronization with a distributed transaction

Both approaches let the application choose commit order, yet both retain a **partial commit window**:

| Property | DB-first | Kafka-first |
|---|---|---|
| First commit | Database | Kafka |
| Second commit | Kafka | Database |
| When second commit fails | DB saved, event may be missing. | Event exists, DB row may be missing. |
| Can the first commit roll back? | No, once the DB commit completed. | No, once the Kafka commit completed. |
| Atomic DB + Kafka guarantee | No. | No. |

Having both managers in the same JVM or the same service call does not alter that fact. When the requirement is "once the DB commits, the event must eventually appear even if the process dies immediately," use a **publish intent durably persisted inside the DB transaction**.

## 8. Transactional outbox is the solution with clear boundaries

Transactional outbox places both the business change and the event publish intent into **the same database transaction**. Publishing to Kafka is performed by an independent worker or CDC connector after the DB commit.

```text
POST /orders
      |
      v
BEGIN DATABASE TRANSACTION
      |
      +--> INSERT orders(...)
      |
      +--> INSERT outbox_events(...)
      |
      v
COMMIT DATABASE TRANSACTION
      |
      v
Outbox worker / CDC
      |
      v
Kafka orders.created
```

If the DB transaction rolls back, both the order row and outbox row roll back. If the DB transaction commits and the process crashes before Kafka publishing, the outbox row remains for a worker to emit later. The core difference is that **the intent to publish an event is never lost from the database** once business state commits.

### Example PostgreSQL schema

```sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_pending
    ON outbox_events (created_at)
    WHERE status = 'PENDING';
```

This example uses an outbox table for a polling model. With CDC, you may choose a different schema and tracking mechanism depending on the connector; a `status` column as shown here is not always required.

### Service creating the order and outbox event

```java
@Service
public class OutboxOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OutboxOrderService(
            OrderRepository orders, OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public Order create(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));

        outbox.save(OutboxEvent.pending(
                UUID.randomUUID(),
                "Order",
                order.getId(),
                "OrderCreated",
                toJson(order)));

        return order;
    }
}
```

`OutboxEvent` and the repository types are domain components to define. Kafka does not appear directly in this transaction; **both changes that must be atomic reside in the same database**.

## 9. Outbox publisher and the at-least-once boundary

The worker reads `PENDING` rows, sends to Kafka, and marks `PUBLISHED` after confirming an appropriate send result:

```text
Outbox row PENDING
       |
       v
Publish Kafka event
       |
       v
Confirm send/publish outcome
       |
       v
Mark outbox row PUBLISHED
```

If the worker crashes **after Kafka publish succeeds and before marking `PUBLISHED`**, the next run can resend the event. This is why transactional outbox normally guarantees **at-least-once delivery**, not that each consumer processes the event once by itself.

Operational principles:

- Use a **stable event ID**, kept identical across all publish retries.
- Downstream consumers must implement **idempotency** by event ID.
- If multiple workers run concurrently, use safe claim/lease mechanisms—such as `SELECT ... FOR UPDATE SKIP LOCKED` in an appropriate transaction—to reduce contention.
- Retry with backoff and track attempt counts; never retry infinitely inside an HTTP request.
- Monitor pending row count and the age of the oldest unpublished row.
- Have a procedure for events failing serialization, schema checks, or Kafka write permissions.
- Implement retention/cleanup for completed outbox rows per audit and replay policies.

**Never mark `PUBLISHED` before publish is confirmed** just to avoid duplicates: crashing after marking and before publishing can cause permanent event loss.

## 10. CDC and Debezium for the outbox

Instead of writing a polling worker, you can use Change Data Capture (CDC), such as a Debezium connector, to detect committed outbox rows from the database transaction log.

```text
Spring service
     |
     v
PostgreSQL COMMIT (orders + outbox_events)
     |
     v
PostgreSQL WAL
     |
     v
CDC connector / Outbox Event Router
     |
     v
Kafka topic
```

Advantage: no need to hold HTTP requests waiting on Kafka, and the connector emits events from committed DB changes. In return, you must operate the connector, replication slots, WAL retention, schema mapping, lag, and retry policies. CDC can still emit duplicate records on certain restart scenarios; idempotent consumers remain an important requirement.

## 11. Inbox / idempotent consumer

A Kafka consumer can receive the same event multiple times when:

- The outbox worker publishes successfully and crashes before updating status.
- The consumer processes successfully and crashes before committing the offset.
- Operators replay a DLT or reset offsets.
- Clients are uncertain of commit results due to dropped connections.

Example processing-marker table:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

In the same DB transaction, the consumer records the event ID and applies the business change:

```java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void onOrderCreated(OrderCreated event) {
    boolean inserted = processedEvents.tryInsert(
            "shipping-service", event.eventId());
    if (!inserted) {
        return;
    }

    shipmentRepository.createShipment(event);
}
```

`tryInsert` must rely on a unique constraint and atomic conflict handling, not merely checking `exists()` and then inserting without a constraint. If the database committed while the Kafka offset did not commit, redelivery is recognized as already processed, avoiding creating a second shipment.

## 12. Kafka EOS for outputs and offsets does not extend to the database

In Kafka → process → Kafka flows, Spring Kafka can place **output records and input offsets** into the same Kafka transaction:

```text
Kafka input
     |
     v
Transactional @KafkaListener
     |
     +--> KafkaTemplate.send(output)
     |
     +--> sendOffsetsToTransaction(...)
     |
     v
Kafka transaction COMMIT / ABORT
```

When the transaction aborts, `read_committed` consumers do not see aborted outputs and the offset does not commit in that transaction. This is a Kafka-to-Kafka exactly-once guarantee for outputs/offsets, **not atomicity with PostgreSQL**.

If a listener both updates a database and sends Kafka outputs, the DB commit can still succeed while the Kafka transaction aborts. The input is then redelivered and can update the database a second time. You need inbox/idempotency, an outbox, or another synchronization mechanism.

With transactional listeners, error handling must align with `AfterRollbackProcessor` and the container's rollback policy. Never swallow exceptions causing the container to treat a failed record as successful and wrongly commit outputs/offsets.

## 13. Choosing a model by required reliability

| Business goal | Approach | What else is needed |
|---|---|---|
| Willing to risk one-sided commits and reconcile | DB-first synchronization. | Monitoring, reconciliation, idempotency. |
| Consumers can receive events before DB state is ready | Nested Kafka-first transaction. | Eventual consistency, compensation, idempotency. |
| Once DB commits, publish intent must survive crashes | Transactional outbox. | Worker/CDC, at-least-once, consumer dedupe. |
| Consumer updates DB from Kafka events | Inbox / idempotent processing. | Unique key, marker and DB side effect in same transaction. |
| Pure Kafka read and Kafka write | Kafka transaction covering outputs and offsets. | `read_committed`, transaction manager, recovery. |
| Multi-service, multi-resource workflow | Saga / compensation. | State machine, timeouts, compensating events, reconciliation. |

For events involving payments, shipping, inventory, or workflows where missing an event causes significant damage, a transactional outbox with retries and monitoring is usually far more appropriate than best-effort coordination of two local commits.

## 14. Common failure scenarios

| Symptom | Possible cause | What to check |
|---|---|---|
| DB has order, Kafka lacks event | DB-first partial commit or producer/transaction commit failure. | Producer errors, transaction result, event ID, reconciliation/outbox. |
| Kafka has event, DB lacks order | Kafka-first committed before DB; DB transaction rolled back. | Commit order, DB logs, retry/compensation. |
| Retry creates two orders | Non-idempotent request, missing unique constraint. | Add business request key and atomic DB writes. |
| Duplicate Kafka events | Outbox publisher crashed after publish or consumer replay. | Use durable event IDs and inbox dedupe. |
| `@Transactional` has no effect on nested method | Self-invocation bypassed Spring proxy, or wrong manager picked. | Call via another bean, inspect proxies and transaction managers. |
| `ProducerFencedException` after rollout | Duplicate transaction ID prefix across pods. | Verify per-instance producer factory prefix/suffix. |
| Outbox pending rows growing | Worker/CDC failure, broker unavailable, or serializer/ACL error. | Check backlog age, publisher logs, and Kafka send results. |
| Consumer wrote to DB, offset did not advance | DB and Kafka commits are separate; consumer restarted/rebalanced. | Use inbox idempotency and inspect committed offsets. |

When debugging, never conclude from a single log line "KafkaTemplate.send() called." You need to know whether the broker received the record, whether the Kafka transaction committed, and which isolation level downstream consumers use.

## 15. Runbook: DB committed, Kafka event missing

Suppose the service saved `orderId=ord-4782`, yet downstream has not seen `OrderCreated`.

1. **Identify the transaction model.** Are you using synchronization, Kafka-first, or outbox? Never conflate logs and behavior across the three models.
2. **Inspect DB state.** Look up the order by business ID and idempotency key; note the DB commit timestamp.
3. **Inspect the producer.** Check serialization, ACL, timeout, coordinator, abort, and fencing errors. Never treat HTTP 500 as proof the DB rolled back.
4. **Search Kafka by event ID.** Look in the right cluster/topic. For transactional outputs, inspection consumers should use `read_committed`.
5. **If using an outbox**, inspect `PENDING` rows, claims/leases, attempts, CDC/worker errors, and backlog age. Fix the publisher before manually publishing.
6. **If using synchronous dual-write**, confirm the partial commit, reconcile, and emit a compensating/missing event with the same event ID; do not recreate the order.
7. **Verify downstream**, confirming records were processed and business effects appeared, not merely producer send counts.

Never reset offsets or bulk replay before knowing whether the event already committed in Kafka; doing so can create unintended duplicates.

## 16. Runbook: Kafka event exists, database rolled back

This is the risk with Kafka-first or when a publisher sits outside the intended DB transaction:

1. Check `@Transactional` and actual transaction managers on both publisher and DB methods.
2. Confirm the nested Kafka transaction really passed through a Spring proxy rather than self-invocation.
3. Check database constraint violations, deadlocks, transaction timeouts, or rollback-only flags.
4. Verify the event in Kafka is **committed**, rather than an aborted record seen by a `read_uncommitted` consumer.
5. If the event committed while DB state is absent, emit a compensating event or reconstruct state by business ID with idempotency.
6. Re-evaluate commit order and architecture; switch to outbox if downstream requires DB state to exist prior to the event.

A committed Kafka record cannot be "undone" by a subsequent PostgreSQL rollback. Compensation is **a new business event**, not erasing Kafka history.

## 17. Production observability

Monitor both Kafka and the database rather than watching producer throughput alone:

- DB transaction commit/rollback rates and deadlock/constraint errors.
- Kafka producer send errors, commit/abort rates, timeouts, and `ProducerFencedException`.
- Outbox pending count, oldest pending age, attempts, and publish failures.
- CDC connector status, lag, replication slots/WAL retention if used.
- Consumer lag, DLT ingress, duplicate events skipped by inbox.
- Reconciliation mismatches between DB state and downstream events.

Example application-defined log:

```text
event=order_created
order_id=ord-4782
event_id=6c4de23b-6e99-4e89-9695-2586e8ce8840
db_transaction=COMMITTED
outbox_status=PENDING
kafka_publish_status=NOT_YET_CONFIRMED
```

Never set `kafka_publish_status=COMMITTED` merely because `send()` returned a future. When using Kafka transactions, check the transaction commit outcome. The metric and log names above are instrumentation suggestions, not default Spring Kafka names.

## 18. Migrating away from ChainedKafkaTransactionManager

When encountering legacy code using `ChainedKafkaTransactionManager`, follow this sequence:

1. Identify all `ChainedKafkaTransactionManager` beans, listener containers, transaction managers, and `KafkaTemplate` beans involved.
2. Clarify the current **commit order**, transaction types opened during requests, and side effects outside Kafka/DB.
3. Build a crash matrix: before commit, between the two commits, after commit, and unknown-outcome timeouts.
4. Choose the replacement model based on reliability requirements: synchronized local transactions or outbox/inbox.
5. For Spring synchronization, use `@Transactional(transactionManager="dataSourceTransactionManager")` and a transactional `KafkaTemplate`. For Kafka-first, extract the nested method to a separate bean.
6. For outbox, implement schema, event IDs, worker/CDC, retries, monitoring, deduplication, and reconciliation.
7. Run fault-injection tests: Kafka down after DB commit, DB deadlock after Kafka publish, pod crashes, producer fencing, and replays.
8. Roll out with monitoring for mismatches, outbox backlogs, DLTs, and duplicate side effects.

Never replace the chained class with a hand-written wrapper that still calls two `commit()` methods and call it an "atomic manager." That change keeps the dual-write failure window intact without adding any guarantees.

## 19. Design and implementation checklist

- [ ] Clearly identified which system is the business **source of truth**.
- [ ] Do not treat `ChainedKafkaTransactionManager` as XA or an atomic distributed commit.
- [ ] Explicitly specify the manager in `@Transactional` when both DB and Kafka managers exist.
- [ ] `KafkaTemplate` uses a transactional producer factory if Kafka transactions are required.
- [ ] Transaction ID prefixes do not collide across concurrently running instances.
- [ ] Behavior during crashes **between the two commit steps** is documented.
- [ ] Request idempotency keys, durable event IDs, and unique constraints are in place.
- [ ] If events must not be lost after DB commit, use transactional outbox or an equivalent durable publish-intent mechanism.
- [ ] Outbox publisher/CDC has retries, backoff, monitoring, and duplicate handling.
- [ ] Consumers have inbox/deduplication for DB operations that must not execute twice.
- [ ] Runbooks exist for reconciliation, replay/DLT, and corresponding operational permissions.
- [ ] Tested pod crashes, broker outages, database rollbacks, and ambiguous commit outcomes.

## 20. Conclusion

`ChainedKafkaTransactionManager` cannot make Kafka and a database commit atomically like an XA transaction. Avoiding reliance on this class exposes the true boundaries of each resource and leads to choosing appropriate recovery strategies.

If you only need **best-effort transaction synchronization**, Spring Kafka supports `KafkaTemplate` joining transactions coordinated by the database manager, with the risk that the Kafka commit after the DB can fail. If the requirement is **once the database commits, event publish intent must survive crashes**, transactional outbox paired with inbox/idempotency is the far more reliable model. Reliability comes from durable data, retries, and verifiable reconciliation—not from putting two transaction managers under a single class name.
