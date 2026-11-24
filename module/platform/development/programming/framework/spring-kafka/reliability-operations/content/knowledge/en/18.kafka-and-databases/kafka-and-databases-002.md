# DB-first commit order

In a Spring Kafka application, business logic often needs to **write to a database and publish a Kafka event** within the same operation: creating an order in PostgreSQL and publishing `OrderCreated`, updating inventory and publishing `InventoryReserved`, or consuming a Kafka record, writing the result to a database, and confirming the offset. The challenge is that the database transaction and the Kafka transaction belong to **two independent systems**.

**DB-first commit order** is the strategy in which **the database transaction commits first and the Kafka transaction commits second**. Spring Kafka can coordinate transactions in this order using transaction synchronization; a transactional Kafka listener flow can also achieve a similar order when the inner database transaction completes before the container's Kafka transaction.

DB-first order makes it clear when data in the database becomes durable. However, **DB-first is not an atomic distributed transaction**. If the database commits but the Kafka commit fails, the database cannot roll back automatically. This is a critical reliability gap that requires designing recovery, idempotency, and often a **transactional outbox**.

## 1. Why does commit order matter?

Consider a service handling an order creation request:

~~~text
HTTP POST /orders
       |
       v
OrderService.createOrder()
       |
       +---- INSERT INTO orders ...
       |
       +---- KafkaTemplate.send("orders.created", ...)
       |
       v
Return result to client
~~~

In code, the `INSERT` statement may execute before `send()`. However, **method call order does not equal transaction commit order**:

- `jdbcTemplate.update(...)` executes SQL inside a database transaction, not necessarily committed yet.
- `kafkaTemplate.send(...)` sends a record through the Kafka producer; with a transactional producer, the record is not yet a committed output for `read_committed` consumers.
- The transaction manager and transaction synchronization determine **when** the database commits and when Kafka commits.

If the database commits first and Kafka commits second, the system is **DB-first**. If Kafka commits before the database, the system is **Kafka-first**. Both orders have a failure window between the two commits.

### 1.1. Ideal goal vs. reality

The typical business expectation is:

~~~text
DB has order O-1001  <=>  Kafka has event OrderCreated(O-1001)
~~~

With two independent transactions, this two-way condition is **not guaranteed atomically** simply by using `@Transactional` or `KafkaTransactionManager`. Even when both are synchronized within one Java thread, a failure can still occur after the first system commits and before the second system commits.

## 2. How does DB-first actually happen?

Suppose a method is managed by `DataSourceTransactionManager`, while `KafkaTemplate` uses a transactional `ProducerFactory` and synchronizes the Kafka transaction with the active database transaction.

~~~text
                        Request-handling thread
                                 |
             begin DB transaction (primary transaction)
                                 |
                        INSERT / UPDATE DB
                                 |
                        KafkaTemplate.send()
                                 |
              Kafka transactional send (uncommitted)
                                 |
                        Method completes normally
                                 |
                    [1] COMMIT DATABASE
                                 |
                    [2] COMMIT KAFKA TRANSACTION
                                 |
                      Complete service call
~~~

The two commits are independent operations against different resources:

1. **Database commit:** SQL changes are durably persisted according to the database's durability guarantees.
2. **Kafka transaction commit:** Kafka records belonging to the transaction are marked committed; any offsets sent into the transaction (if applicable) also commit with the Kafka outputs.
3. If step 2 fails, **step 1 is not automatically reversed**.

Kafka does not participate in a shared XA/2PC transaction with the database in this Spring Kafka transaction synchronization model. Transaction synchronization is a mechanism for **ordering lifecycles** across resources, not an atomic commit protocol linking two coordinators.

## 3. Configuring a producer with Kafka transactions

For `KafkaTemplate` to actually participate in a Kafka transaction, the producer factory must be configured with a transactional ID. In Spring Boot, for example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: "orders-instance-a-tx-"
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

`transaction-id-prefix` causes the producer factory to manage transactional producers. Spring Kafka constructs full transactional IDs from the prefix and a suffix; you must ensure **no two active-active instances produce duplicate transactional IDs**.

In production, `orders-instance-a-tx-` is only an illustrative name. The prefix must be derived from a stable instance/worker identity within the concurrent operating scope and follow an appropriate fencing strategy. When using a container orchestrator, account for rollout overlap and transactional ID reuse.

`acks=all` ensures the broker acknowledges writes according to replication policy, but **it does not make database and Kafka commits atomic**. A record accepted by a broker inside a Kafka transaction does not mean the transaction has committed.

### 3.1. Which transaction manager is primary?

If an application has both `DataSourceTransactionManager` and `KafkaTransactionManager`, an unqualified `@Transactional` can be ambiguous or depend on Spring's bean selection. With DB-first, explicitly designate the database transaction manager as the **primary transaction** at the business entry point.

Example of declaring an explicit transaction manager name:

~~~java
@Configuration
public class DatabaseTransactionConfiguration {

    @Bean("dataSourceTransactionManager")
    public DataSourceTransactionManager dataSourceTransactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

In a JPA application, the database transaction manager may be `JpaTransactionManager` instead of `DataSourceTransactionManager`. What matters is that the annotation points to the exact transaction manager governing the data writes.

Spring Boot can auto-configure a transaction manager when conditions are met; there is no need to define an extra bean if the application already has the right manager. The snippets in this lesson only illustrate the components that must be wired, not the sole auto-configuration setup.

## 4. Example of DB-first @Transactional with KafkaTemplate

A service receives a command, saves the order, and emits an event:

~~~java
@Service
public class OrderCommandService {

    private final JdbcTemplate jdbcTemplate;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderCommandService(
            JdbcTemplate jdbcTemplate,
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public void createOrder(CreateOrder command) {
        jdbcTemplate.update(
                "INSERT INTO orders (id, status) VALUES (?, ?)",
                command.orderId(),
                "NEW");

        OrderCreated event = new OrderCreated(command.orderId(), "NEW");
        kafkaTemplate.send("orders.created", command.orderId(), event);
    }
}
~~~

Assume `CreateOrder` and `OrderCreated` are business Java records/DTOs, the database schema already has the `orders` table, the Kafka producer has transactions enabled, and `KafkaTemplate` is backed by a transactional producer factory.

When the service is invoked through the Spring proxy and the database transaction starts:

1. `createOrder()` begins the database transaction.
2. SQL writes the order without committing yet.
3. `KafkaTemplate` uses a transactional producer synchronized with the active transaction.
4. When the method returns normally, Spring **commits the DB first**.
5. Then Spring **commits the synchronized Kafka transaction**.
6. If the Kafka commit succeeds, both the database state and the Kafka event are confirmed.

### 4.1. Conditions for this example to work properly

- Call the method through a **Spring proxy**; self-invocation within the same class typically bypasses the `@Transactional` interceptor.
- Database operations must use the same transactional resource managed by the DB manager.
- The Kafka producer factory must have `transactionIdPrefix` configured with a matching `KafkaTemplate`.
- Do not casually call `KafkaTemplate.executeInTransaction(...)` inside the method and expect the inner transaction to follow the same DB-first order; that API manages transactions in its own way.
- If the Spring context has multiple transaction managers, specify the manager explicitly in the annotation.
- Serializers and partition keys must match the actual event; a serialization error before commit can fail the method.
- To verify transaction visibility, use a consumer with `isolation.level=read_committed`.

If you need to await the Kafka send result, you can inspect the future per your Spring Kafka version's API, but understand that **Kafka send acknowledged does not mean Kafka transaction committed**.

## 5. Why does send() succeeding still not guarantee the outcome?

`KafkaTemplate.send()` normally returns a future representing the send result. The Kafka producer can receive a broker acknowledgment that the record has been written to the log within the transaction.

~~~text
KafkaTemplate.send()
        |
        v
Broker writes record with transaction metadata
        |
        v
Producer receives send acknowledgment
        |
        v
Kafka transaction is still open
        |
        +---- commit succeeds -> read_committed consumer sees it
        |
        +---- abort / timeout -> read_committed consumer skips it
~~~

Therefore:

- The `send()` future can complete **before** the Kafka transaction commits.
- `acks=all` does not replace `commitTransaction()`.
- If the Kafka commit runs after the DB commit and fails, the database can still contain the order while the event remains uncommitted.
- If the network drops right at commit time, the application may **not know for sure** whether the broker committed or not.

Never use `send().get()` or `send().join()` as proof that the database and Kafka committed atomically.

## 6. Failure windows of DB-first

The easiest mistakes occur around different points in time:

| Failure point | Database | Kafka event | What must be handled |
|---|---|---|---|
| Before DB transaction commit | Can roll back | Kafka transaction uncommitted; needs proper abort/timeout | Retry the operation per business semantics. |
| After DB commit, before Kafka commit | **Committed** | Uncommitted, or final outcome unknown | DB/Kafka gap exists; reconciliation/recovery mechanism required. |
| Kafka commit returns explicit error | **Committed** | Likely uncommitted; depending on error, outcome may be unknown | Do not assume DB rolled back or that the event was definitely lost. |
| Both DB and Kafka committed, response lost | **Committed** | **Committed** | Client retry can create duplicate commands/events without idempotency. |
| Process killed right after DB commit | **Committed** | Kafka transaction may be uncommitted; broker handles timeout/fencing | On restart, there must be a path to republish the missing event. |

### 6.1. Failure before database commit

For example, SQL violates a unique constraint or the service throws an exception before the method finishes. The database transaction can roll back. The synchronized Kafka transaction must also end accordingly; uncommitted records are not treated as valid output by `read_committed` consumers.

This case is usually easier to recover from because the database has not yet persisted the new change.

### 6.2. Database commit succeeds, Kafka commit fails

This is the **DB-first failure window**:

~~~text
INSERT order O-1001
        |
        v
DB COMMIT succeeds
        |
        v
Kafka COMMIT fails / times out
        |
        +---- DB still has O-1001
        |
        +---- orders.created may not have a committed event yet
~~~

On the application side, an exception may be thrown during transaction synchronization completion. Modern Spring Kafka versions propagate secondary Kafka commit errors to the caller so the application can execute a **compensating action**. Older versions sometimes logged certain post-primary-commit errors differently; evaluate the behavior of the exact version you run.

**A secondary commit error cannot undo a primary DB commit that already succeeded.** Do not catch the exception and attempt to "roll back the DB" on the already-closed transaction.

### 6.3. Uncertain Kafka commit outcome

A network error right after sending the commit request is an "unknown outcome": the broker may have processed the commit, with the response lost before reaching the producer. If the application immediately sends a fresh event with a new producer, **it can create a duplicate**.

Recovery design should use a stable event ID, state tracking, and idempotent handling; never assume "exception = Kafka definitely does not have the event."

## 7. Does Kafka-first solve the problem?

If you reverse the order so Kafka commits before the database, the risk simply moves to the other side:

~~~text
Kafka transaction COMMIT
           |
           v
Database COMMIT
           |
           +---- database commit fails
           |
           +---- event is visible, but DB does not yet have corresponding state
~~~

Kafka-first suits certain workflow requirements, but it does not solve cross-system atomicity. In Spring, you can coordinate the order using nested transactional methods and distinct transaction managers, yet that approach still has a failure window between the two commits.

| Commit order | Primary failure window |
|---|---|
| **DB-first** | New DB state exists, but Kafka event is not yet committed/confirmed. |
| **Kafka-first** | Kafka event is committed, but corresponding DB state has not committed. |

Thus, choosing DB-first usually comes from treating **the database as the source of truth**, not from any proof that the workflow achieves end-to-end exactly-once semantics.

## 8. DB-first in a Kafka consumer updating a database

Another common variant: the listener container opens a Kafka transaction, while database work happens inside a method with its own database transaction. The database method completes before the listener container commits its Kafka transaction.

~~~text
Kafka listener container opens Kafka transaction
              |
              v
Listener calls dbWriter.apply(event)
              |
              v
Database transaction begins
              |
              v
INSERT / UPDATE / UPSERT
              |
              v
DATABASE COMMIT when dbWriter.apply() returns
              |
              v
Listener can send Kafka output
              |
              v
Kafka listener transaction COMMIT
(Kafka output + input offset)
~~~

Example splitting two Spring beans so the database `@Transactional` is intercepted by the proxy:

~~~java
@Service
public class OrderDatabaseWriter {

    private final JdbcTemplate jdbcTemplate;

    public OrderDatabaseWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public void apply(OrderEvent event) {
        jdbcTemplate.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                event.status(),
                event.orderId());
    }
}
~~~

The listener uses a Kafka container configured with a transaction manager:

~~~java
@Component
public class OrderKafkaListener {

    private final OrderDatabaseWriter dbWriter;
    private final KafkaTemplate<String, OrderProcessed> kafkaTemplate;

    public OrderKafkaListener(
            OrderDatabaseWriter dbWriter,
            KafkaTemplate<String, OrderProcessed> kafkaTemplate) {
        this.dbWriter = dbWriter;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.in",
            containerFactory = "transactionalListenerFactory")
    public void handle(ConsumerRecord<String, OrderEvent> record) {
        dbWriter.apply(record.value()); // DB commits when this method completes

        kafkaTemplate.send(
                "orders.processed",
                record.key(),
                new OrderProcessed(record.value().orderId()));
    }
}
~~~

In this case, understand that **the two transactions are nested in lifecycle**, not merged into an XA transaction:

- The DB commit may already have happened when `dbWriter.apply()` returns.
- The container's Kafka transaction commits after the listener finishes, including Kafka outputs and input offsets if configured properly.
- If the Kafka transaction aborts or the producer is fenced, the input offset may remain uncommitted and the record will be redelivered.
- On redelivery, the database operation can execute a second time unless idempotency is enforced.

Note: This is **one way to achieve DB-first**, distinct from the example where a service opens a **DB primary transaction** and uses Kafka resource synchronization. Distinguish the two models when reading stack traces, logs, and designing recovery.

## 9. Consumer redelivery and database idempotency

Suppose a listener processes `PaymentAuthorized(id=E-100)`:

~~~text
Consumer reads E-100
      |
      v
DB UPDATE succeeds, COMMIT
      |
      v
Kafka offset commit fails
      |
      v
Consumer restarts / rebalances
      |
      v
E-100 is redelivered
      |
      v
Duplicate DB UPDATE
~~~

If the SQL only sets `SET status = 'AUTHORIZED'`, re-running it may not cause extra side effects. However, if it executes `balance = balance - amount` or inserts another payment transaction, repetition can cause serious data corruption.

One solution is an **inbox/deduplication table** with a unique constraint keyed by consumer and event ID. The business update and the processed-marker insert must reside **in the same database transaction**:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

PostgreSQL example:

~~~java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void applyOnce(PaymentAuthorized event) {
    int inserted = jdbcTemplate.update(
            """
            INSERT INTO consumed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "payments-consumer",
            event.eventId());

    if (inserted == 0) {
        return; // Event already applied in DB
    }

    jdbcTemplate.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            event.amount(),
            event.accountId());
}
~~~

The SQL and Java snippets use PostgreSQL and modern Java text blocks. If the business update throws an exception, **the entire DB transaction** rolls back, including the marker in `consumed_events`. If a duplicate arrives after the DB commit, the marker skips the business side effect. For other consumers, use a separate namespace (`consumer_name`) if business logic requires each consumer to apply the event independently.

This is **idempotent DB processing**; it does not completely eliminate duplicate Kafka events, but it enables the business to tolerate at-least-once delivery across the DB-first gap.

## 10. Transactional outbox: the preferred approach for reliable event publishing

If the requirement is "every durable database change must have an event eventually published," pure DB-first transaction synchronization has a weakness: **after the DB commit and before the Kafka commit, there is not necessarily durable evidence to republish a missing event**.

**Transactional outbox** closes this gap by storing both business state and **the intent to publish an event** in the *same database transaction*.

~~~text
Business request
       |
       v
DB transaction
       |
       +---- INSERT/UPDATE orders
       |
       +---- INSERT outbox_events(event_id, payload, ...)
       |
       v
DB COMMIT (business + outbox atomic)
       |
       v
Outbox publisher / CDC reads unpublished events
       |
       v
Kafka publish
       |
       v
Mark as published or checkpoint CDC
~~~

If the DB rolls back, both business state and the outbox record roll back. If Kafka is temporarily unavailable, **the outbox record remains in the DB** to be retried when the system recovers.

### 10.1. Example outbox schema

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL
);
~~~

The schema above illustrates PostgreSQL. A production system may also need state, retry count, partition key, last publish error, lease/claim fields, or retention/archival policies.

The business service writes both row types in one DB transaction:

~~~java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void createOrder(CreateOrder command) {
    UUID eventId = UUID.randomUUID();

    jdbcTemplate.update(
            "INSERT INTO orders (id, status) VALUES (?, ?)",
            command.orderId(), "NEW");

    jdbcTemplate.update(
            """
            INSERT INTO outbox_events (
                event_id, aggregate_type, aggregate_id, event_type, payload
            ) VALUES (?, ?, ?, ?, ?::jsonb)
            """,
            eventId,
            "Order",
            command.orderId(),
            "OrderCreated",
            serializeOrderCreated(command, eventId));
}
~~~

There is no need to call Kafka inside this transaction. Once the DB commit succeeds, the event intent is durably stored alongside the order.

### 10.2. Publisher and the duplicate window

An outbox publisher typically:

1. Selects events not yet successfully sent.
2. Publishes them to Kafka with a **stable event ID**.
3. Confirms the Kafka publish/transaction per the mechanism in use.
4. Marks the row as published.

If the Kafka publish succeeds but the process crashes **before updating `published_at`**, the row will be sent again. Therefore, outbox by default provides **at-least-once publishing**, not strictly once across all failure modes.

The right design is **outbox + stable event ID + idempotent consumer**. If multiple outbox workers run concurrently, use safe claiming/locking—such as `FOR UPDATE SKIP LOCKED` with appropriate timeouts/recovery—to avoid contention and reduce unnecessary duplicates.

You can use **Change Data Capture (CDC)**, such as the Debezium outbox pattern, instead of a polling publisher. Whether choosing CDC or polling, you still need to account for duplicate delivery, per-aggregate ordering, schema evolution, and monitoring.

## 11. When is direct DB-first still reasonable?

Not every application needs an outbox. DB-first transaction synchronization can be sufficient when:

- The Kafka event is only used for cache invalidation or notifications that are easy to regenerate.
- The system has a periodic reconciliation job that republishes missing events.
- Business requirements tolerate a brief gap between DB state and the Kafka event.
- Events carry an idempotency key and have a clear recovery procedure.
- Dedicated metrics and alerts exist for Kafka commit failures after DB commits.

However, for events critical to payments, shipping, fulfillment, ledgers, or data pipelines where business events must not be lost, **outbox is usually safer**. It turns the "intent to publish an event" into durable data inside the primary DB commit.

Do not choose synchronous DB-first just to have fewer tables if you lack a way to recover when the DB commits but Kafka does not receive the event.

## 12. Recovery and reconciliation on partial commit

If you run DB-first without an outbox and encounter a Kafka commit failure, the fix is not simply rolling back the committed DB. You need a concrete procedure:

1. **Record state:** correlation ID, order ID, DB commit timestamp, Kafka transaction ID, and exception.
2. **Classify the Kafka result:** did the commit definitely fail, or is the **outcome unknown** due to timeout/network?
3. **Look up event ID:** verify whether the event reached downstream via reliable tracking; do not infer solely from the application throwing an exception.
4. **Recover from source of truth:** reconstruct the event from DB state or a durable event ledger/outbox if available.
5. **Republish with the same event ID**, paired with consumer deduplication.
6. **Reconcile state:** observe Kafka consumer progress and confirm downstream applied the event.

If the database only stores current state, reconstructing the exact historical event may be impossible. For instance, if an order's status has changed multiple times, reading the latest state after an incident is not enough to recreate the event "when did the order transition from NEW to PAID." This is a strong reason to persist a durable outbox/event history as the transaction occurs.

### 12.1. Do not blindly retry HTTP commands

If a client receives HTTP 500 because the Kafka commit failed **after the DB commit**, the client may resend the request. If the create-order command lacks a unique business key or idempotency key, the application could create two orders.

Design write APIs with idempotency keys, unique constraints, and the ability to return the result of an already-processed command. An error reply after a DB commit should be interpreted as "overall state uncertain," not that the DB remained unchanged.

## 13. Commit order and listener container rollback

In a transactional Kafka listener flow:

- The container's Kafka transaction manages Kafka outputs and consumer offsets when configured properly.
- A DB transaction managed by another service may commit **before** the Kafka transaction.
- If the business service throws an exception, the DB transaction rolls back, and the listener exception can roll back the Kafka transaction.
- If the DB commit succeeds but the Kafka transaction aborts, the input record can be redelivered and needs idempotency.
- `AfterRollbackProcessor` handles seek/recovery after a Kafka rollback, but **does not roll back an already-completed DB commit**.

For poison records, DLT recovery allows the Kafka offset to move forward. However, before routing a record to the DLT, check whether the DB has already persisted any side effects. If the DB committed while the Kafka offset did not, replaying from the DLT and redelivering from the main topic can cause duplicate processing.

Kafka exactly-once semantics protect the Kafka boundary; the database transaction does not automatically join the same transaction coordinator.

## 14. Why avoid ChainedKafkaTransactionManager?

Some legacy Spring Kafka codebases use `ChainedKafkaTransactionManager` or chain transaction managers to enforce commit order. Such chaining **is not distributed two-phase commit** and cannot eliminate the gap when the first resource commits and the second fails.

`ChainedKafkaTransactionManager` has been deprecated in the Spring Kafka ecosystem. For new applications, consider supported transaction synchronization or an outbox architecture rather than treating a chained manager as an exactly-once solution between Kafka and a database.

A chained commit order can make lifecycle handling convenient, but must not be mistaken for an end-to-end atomicity guarantee.

## 15. Observing DB-first in production

The system should distinguish at least three states:

~~~text
BUSINESS_DB_COMMITTED
KAFKA_EVENT_COMMITTED
DOWNSTREAM_PROCESSED
~~~

A request may reach the first state without reaching the second; a Kafka event may commit without downstream having processed it yet. Therefore, a "request successful" metric is not enough to conclude the end-to-end pipeline is healthy.

Signals to monitor:

| Signal | Meaning |
|---|---|
| DB commit success/error | Whether the primary transaction persisted reliably. |
| Kafka transaction commit error | Failures occurred in the secondary Kafka commit step. |
| Unknown Kafka commit outcome | Requires reconciliation; avoid non-idempotent resends. |
| Outbox pending count and oldest age | Number of events awaiting publish and maximum delay. |
| Outbox publish/retry/DLT rate | Throughput of moving events from DB to Kafka. |
| Consumer lag by topic/partition | Whether downstream is keeping up with incoming data. |
| Duplicate event/business command rate | Whether idempotency keys and deduplication are working. |
| Reconciliation discrepancies | Where DB state and the event stream have diverged. |

Logs/traces should include `orderId`, `eventId`, `transactionName`, Kafka topic/partition when known, and per-step status. Do not log sensitive payloads. Be careful with metric labels using event IDs since cardinality can explode; event IDs belong in structured logs or traces.

Do not log `KafkaTemplate.send()` success and conclude the Kafka transaction commit succeeded. Measure the actual commit boundary.

## 16. Testing commit order and failure windows

Use a real database in Testcontainers and a real Kafka broker to test semantics. Unit tests that only mock `JdbcTemplate` and `KafkaTemplate` cannot prove resource commit order.

Valuable integration scenarios:

1. **Happy path:** DB contains the order; a `read_committed` consumer receives `OrderCreated` after the Kafka commit.
2. **DB rollback:** deliberately trigger a SQL/validation failure before commit; verify no committed Kafka event exists.
3. **Kafka failure after DB commit:** simulate a Kafka commit failure in the window after primary DB commit; verify the DB retains the order and the exception is reported per version behavior.
4. **Process crash in the commit window:** stop the process after DB commit but before Kafka commit; verify reconciliation/outbox requirements.
5. **Unknown outcome:** drop the connection at Kafka commit time; verify retries/recovery do not create business duplicates.
6. **Consumer redelivery:** DB commit succeeds while Kafka listener transaction/offset commit fails; verify the inbox unique key blocks a second update.
7. **Outbox publisher crash:** Kafka received the event, but the outbox row is not yet marked published; verify republishing keeps the same event ID and downstream stays idempotent.
8. **Multiple outbox workers:** contention over the same row; verify locking/claiming prevents unnecessary double work.
9. **Schema/serializer failure:** event cannot be serialized; verify the outbox row is not lost and the error state is explicit.
10. **Rollout/rollback:** old and new versions run concurrently; outbox/events remain readable and compatible with the expected schema version.

To verify "DB commits before Kafka commits," attach hooks/logs observing transaction lifecycle events or inject controlled failures at the secondary commit. Do not rely solely on the order of two lines `jdbc.update()` and `kafkaTemplate.send()` in source code.

Tests should use bounded timeouts, await specific conditions, and avoid long `Thread.sleep()` calls. For Kafka transactions, verification consumers should use `read_committed` to avoid misreading uncommitted or aborted records.

## 17. Common mistakes

- **Assuming `@Transactional` covers both database and Kafka like an XA transaction:** a transaction manager only covers its configured resources and synchronizations.
- **Equating send acknowledgment with Kafka commit:** a broker ack on send does not mean the transaction is complete.
- **Ignoring failures after DB commit:** a secondary Kafka commit failure does not roll back the database automatically.
- **Catching a Kafka commit exception and returning "DB rolled back":** misrepresents the durable state.
- **Retrying commands without an idempotency key:** the DB operation may execute again even though the first attempt committed.
- **Thinking outbox guarantees strict once-only publishing:** the publisher can resend if it crashes after a Kafka ack and before marking sent.
- **Only increasing Kafka retries/backoff when DB/Kafka diverge:** without a durable event to recover from, retries cannot fix every failure window.
- **Using Kafka-first as a cure for DB-first:** reversing the order merely creates the opposite failure window.
- **Changing `transaction-id-prefix` arbitrarily across replicas:** can cause producer fencing if full transactional IDs collide.
- **Omitting `read_committed` when testing transaction visibility:** reads aborted outputs and leads to wrong conclusions.
- **Committing DB in a consumer without redelivery protection:** uncommitted Kafka offsets can cause business state to be applied repeatedly.
- **Storing only current DB state without event intent:** makes reconstructing exact historical events hard after an incident.
- **Assuming `ChainedKafkaTransactionManager` performs 2PC:** chaining does not create an atomic cross-resource commit.

## 18. Choosing DB-first for production

Before deploying a workflow that writes to DB and publishes to Kafka, clarify:

- Is the database or Kafka the business source of truth?
- Can the secondary Kafka commit fail after the DB commit? **Yes**, so where is recovery?
- If the Kafka commit outcome is unknown, are the event ID and deduplication sufficient?
- If the process dies right after the DB commit, what durable data allows publishing the missing event?
- If the Kafka input is redelivered, can the DB operation be applied twice?
- Which transaction manager is actually primary in `@Transactional`?
- Is the Kafka producer using a transactional producer factory and does the listener have the right transaction context?
- How are secondary commit errors captured in logging, alerts, and reconciliation?
- Are transactional outbox and inbox needed to meet SLA and durability requirements?
- Are integration tests in place for partial commits, unknown outcomes, restarts, and duplicate processing?

**DB-first commit order** is a consistent ordering choice: database commits first, Kafka commits second. It simplifies treating the database as the source of truth, but does not make the two resource commits atomic. For business events that must never be lost when a process or Kafka fails, treat **transactional outbox, reconciliation, and idempotent consumers** as core architectural components rather than optional patches.
