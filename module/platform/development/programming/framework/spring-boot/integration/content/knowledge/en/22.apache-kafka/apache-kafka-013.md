# Distinguishing Kafka Transactions from Database Transactions

## 1. Context of a Spring Boot Integration Flow

In a **Spring Boot Integration** service, a single HTTP request may simultaneously create an order in PostgreSQL, update a cache, and emit an `OrderCreated` event via Apache Kafka. Conversely, a `@KafkaListener` may consume an event, persist business data to a database, and confirm the processed offset. Even when these steps live in the same Java method, they do not automatically share **one atomic transaction**.

Example workflow:

1. Receive `POST /orders` with `orderId`.
2. Save the order in `purchase_orders`.
3. Publish an event to `orders.created` for downstream services.
4. Inventory service's consumer reads the event and deducts stock.

The key question is not merely "is `@Transactional` present?" but rather: **which resources are governed by which transaction manager, when does each commit happen, what happens if the process crashes between commits, and will reprocessing cause duplicates?**

~~~mermaid
flowchart LR
    HTTP["HTTP adapter"] --> Service["OrderService"]
    Service --> DB[("PostgreSQL")]
    Service --> Kafka[("Kafka topic")]
    Kafka --> Consumer["Inventory consumer"]
    Consumer --> Stock[("Inventory DB")]
    DB -. "DB transaction" .- Service
    Kafka -. "Kafka transaction" .- Service
~~~

**Lesson scope:** distinguish database transactions from Kafka transactions; understand the limits of exactly-once guarantees; coordinate transactions, error handling, and duplicates; and test and observe real integration flows. Kafka and databases can participate in the same business workflow, yet each transaction has its own boundary.

## 2. What Does a Database Transaction Guarantee?

Relational database transactions group multiple SQL statements into a single consistent unit. **ACID** properties generally mean:

| Property | Business Meaning |
|---|---|
| **Atomicity** | Changes inside the transaction either all succeed together or roll back together |
| **Consistency** | Data constraints and database invariants hold across commits |
| **Isolation** | How uncommitted or committed changes are visible across concurrent transactions depends on isolation level |
| **Durability** | Committed data survives crashes per the database's durability guarantees |

Example PostgreSQL transaction:

~~~sql
BEGIN;

INSERT INTO purchase_orders (id, customer_id)
VALUES ('11111111-1111-1111-1111-111111111111', 'customer-42');

INSERT INTO outbox_events (event_id, aggregate_id, topic_name, payload)
VALUES (
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    'orders.created',
    '{"eventId":"22222222-2222-2222-2222-222222222222","orderId":"11111111-1111-1111-1111-111111111111"}'
);

COMMIT;
~~~

If the second statement violates a constraint and rolls back, the order row is rolled back as well. The benefit of persisting `outbox_events` in the same transaction is detailed below.

In Spring, `@Transactional` selects one `PlatformTransactionManager` (for JDBC/JPA) or `ReactiveTransactionManager` (for R2DBC) and coordinates **operations enlisted with that manager**. For example, `DataSourceTransactionManager`/`JdbcTransactionManager` coordinates compatible JDBC work on one database; `JpaTransactionManager` coordinates the JPA persistence context; `R2dbcTransactionManager` coordinates R2DBC connections via reactive context.

**A database transaction does not automatically encompass** a Kafka send, an HTTP call to another service, or standard Redis updates. Rolling back SQL after Kafka already published successfully cannot "unsend" the Kafka message via database `ROLLBACK`.

## 3. What Does a Kafka Transaction Guarantee?

Kafka provides **transactional producers** to group writes across multiple partitions/topics in the **same Kafka cluster**, and—in consume-process-produce flows—include consumed offsets. Producers use a `transactional.id` and Kafka's transaction API:

~~~text
initTransactions()
beginTransaction()
send(topic_A, record_1)
send(topic_B, record_2)
[sendOffsetsToTransaction(offsets, consumerGroupMetadata) for consume-process-produce]
commitTransaction() or abortTransaction()
~~~

In Spring Kafka, `KafkaTemplate` and listener containers integrate this transaction lifecycle so application code rarely invokes raw producer transaction methods directly. Key points:

- **Kafka commit:** records in the transaction are marked committed and become visible to consumers configured with `isolation.level=read_committed`.
- **Kafka abort:** records from aborted transactions are withheld from `read_committed` consumers. The Kafka log still retains the records and abort markers; aborting is not a physical per-message delete.
- **Offsets in transactions:** in *consume → process → produce*, input offsets commit in the same Kafka transaction as outputs. On abort, outputs stay hidden from `read_committed` and input offsets remain uncommitted so records can be reprocessed.
- **Idempotent producer:** suppresses duplicate records caused by producer retries within Kafka's idempotence scope. It **does not eliminate** duplicate side effects in downstream databases or HTTP APIs.
- **Producer fencing:** when a new producer incarnation initializes with the same `transactional.id`, older incarnations are fenced from committing further transactions. Design `transactional.id` so active concurrent instances never collide.

Default consumers do not automatically wait for transaction commits. To rely on Kafka transaction atomicity when reading, **consumers must set `read_committed`**. With `read_uncommitted`, consumers can observe records from transactions that later abort; ignoring isolation configuration invalidates downstream exactly-once assumptions.

### Exactly-Once Within Kafka Has a Specific Boundary

Suppose a processor reads `orders.raw`, normalizes payloads, and writes `orders.normalized`. If both output records and input offsets commit in the **same Kafka transaction**, reprocessing after a failure avoids emitting duplicate committed outputs along this Kafka path—assuming proper producer, consumer, and transaction configs.

Conversely, if that processor also calls a payment API or updates PostgreSQL, the Kafka transaction **cannot roll back** side effects outside Kafka. Kafka's *exactly-once semantics* never means every external system invoked in the flow executes business logic once.

~~~mermaid
flowchart TD
    Input[("Kafka input topic")] --> Processor["Consume / transform / produce"]
    Processor --> Output[("Kafka output topic")]
    Processor --> Offsets["Input offsets"]
    Tx["One Kafka transaction"] -.-> Output
    Tx -.-> Offsets
    Processor --> SQL[("External database")]
    Tx -. "Not covered" .-> SQL
~~~

## 4. Direct Comparison of the Two Transaction Types

| Criterion | Database Transaction | Kafka Transaction |
|---|---|---|
| Primary resources | Tables, rows, indexes, and changes within the DB transaction | Records sent by producer and offsets enlisted in Kafka |
| Start point | `BEGIN`, transaction manager, or reactive transaction operator | Transactional producer / Kafka transaction manager |
| End point | `COMMIT` or `ROLLBACK` | `commitTransaction` or `abortTransaction` |
| Atomicity | SQL operations enlisted in the same DB transaction | Kafka records and offsets enlisted in the same Kafka transaction |
| Visibility | Governed by DB isolation level, e.g., `READ COMMITTED` | Consumers must use `read_committed` to hide aborted records |
| Failure handling | DB rolls back uncommitted SQL changes | Kafka aborts transaction; outputs hidden from `read_committed` consumers |
| Spring coordination | `JdbcTransactionManager`, `JpaTransactionManager`, `R2dbcTransactionManager` | `KafkaTransactionManager`, listener container, or `KafkaTemplate` |
| Not covered automatically | Kafka publishes, HTTP calls, Redis updates | PostgreSQL commits, HTTP calls, Redis mutations |
| Primary use cases | Consistent business data updates and outbox rows | Atomic multi-record Kafka writes; Kafka-to-Kafka consume-process-produce |

Crucial takeaway: **two transaction managers do not merge into one distributed transaction**. Adding `@Transactional` or enabling Kafka transactions does not make PostgreSQL commit and Kafka commit atomic under a single decision.

## 5. Why Does "Write Database Then Send to Kafka" Leave a Failure Gap?

### 5.1. Database Commit First, Kafka Second

~~~mermaid
sequenceDiagram
    participant S as Spring Boot Service
    participant D as Database
    participant K as Kafka
    S->>D: BEGIN / INSERT order
    S->>D: COMMIT
    D-->>S: OK
    Note over S,K: Service may crash here
    S->>K: Send OrderCreated
    K-->>S: Ack
~~~

If the service crashes after the database commits and before Kafka receives the message, the order exists without its event. Retrying the entire HTTP request may not be safe either: without an idempotency key, a retry could create a second order.

### 5.2. Kafka Commit First, Database Second

~~~mermaid
sequenceDiagram
    participant S as Spring Boot Service
    participant K as Kafka
    participant D as Database
    S->>K: BEGIN / Send OrderCreated / COMMIT
    K-->>S: OK
    Note over S,D: Service may crash here
    S->>D: BEGIN / INSERT order / COMMIT
~~~

If Kafka commits while the database fails to commit, consumers act on an event for a nonexistent order. Using a Kafka transaction for the send does not change this outcome.

### 5.3. Independent Commit Outcome Matrix

| DB Commit | Kafka Commit | Business Consequence |
|---|---|---|
| Succeeded | Succeeded | Happy path, though consumers must still handle retries/redeliveries |
| Succeeded | Failed / not sent | Database updated, downstream missing the event |
| Failed | Succeeded | Event published for a database change that does not exist |
| Failed | Failed | No committed changes in either system |

During network failures, a client can also be **unsure** whether Kafka committed after a timeout. Blindly retrying can duplicate events. Never design a solution assuming every error response proves the message was never written.

Some Spring Kafka setups can synchronize a Kafka transaction with a database transaction in commit order. This is *best-effort one-phase commit*: a gap remains between the two resources, so it does not provide true single-transaction atomicity. You still need recovery logic when one commits and the second fails.

## 6. Kafka-Only Transaction Scenario: Consume → Process → Produce

Suppose an app reads `invoice.input` and writes to two topics: `invoice.validated` and `audit.events`. Enlisting all writes and input offsets into one Kafka transaction ensures `read_committed` consumers never observe partial/aborted outputs.

Spring Boot configuration example (assign a unique `INSTANCE_ID` per concurrently running instance; `local` suits only a single local instance):

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      acks: all
      transaction-id-prefix: "invoice-${INSTANCE_ID:local}-tx-"
      properties:
        enable.idempotence: true
    consumer:
      group-id: invoice-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

With Spring Boot/Spring Kafka transaction support, setting this prefix allows `KafkaTemplate` to obtain transactional producers. Emitting **two output records in one Kafka transaction** from a producer:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceEventPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public InvoiceEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishPair(String invoiceId, String validatedJson, String auditJson) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("invoice.validated", invoiceId, validatedJson);
            operations.send("audit.events", invoiceId, auditJson);
            return null;
        });
    }
}
~~~

Both `send` calls share one Kafka transaction. This illustrates **produce → produce**. Calling this method from inside a `@KafkaListener` does **not automatically** enlist the **consumed input offset** into that transaction unless the listener container itself is configured with a Kafka transaction manager; standalone `executeInTransaction` only wraps its own sends. Use Spring Kafka's transactional listener container support for full Kafka-to-Kafka EOS across consume-process-produce.

Distinguish **producer idempotence** (preventing duplicates on producer transport retries) from **business idempotency** (preventing double inventory deductions or ledger postings when the same `eventId` is reprocessed).

## 7. When Consistency Must Span Database and Kafka: Transactional Outbox

The **transactional outbox** pattern is widely used when a business action must commit to a database and reliably emit an event. Rather than relying on two independent commits on the request path, the service writes **the business row and the publish intent** inside **one DB transaction**; a separate process relays outbox rows to Kafka.

~~~mermaid
flowchart LR
    HTTP["HTTP request"] --> S["OrderService"]
    S --> TX["DB transaction"]
    TX --> O[("purchase_orders")]
    TX --> X[("outbox_events")]
    X --> Relay["Outbox relay / CDC"]
    Relay --> Kafka[("Kafka")]
    Kafka --> C["Consumer"]
    C --> I[("Processed event ID + business change")]
~~~

### 7.1. Illustrative PostgreSQL Schema

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    customer_id VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL REFERENCES purchase_orders(id),
    topic_name VARCHAR(180) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
~~~

`event_id` is an immutable identifier letting consumers recognize already-processed events. `aggregate_id` can serve as the Kafka message key to preserve partition order under consistent partitioning. With multiple concurrent updates per aggregate, maintaining strict business order also requires version/sequence numbers and serialized writes; a shared key alone is not enough.

### 7.2. Writing the Order and Outbox in One Database Transaction

This Spring JDBC example highlights the DB boundary cleanly. Assume the service configures a `JdbcTemplate` and a JDBC transaction manager named `dbTransactionManager` (e.g., `JdbcTransactionManager` for the `DataSource`); bean names must match your configuration.

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(UUID orderId, UUID eventId,
                            String customerId, String eventJson) {
        jdbc.update("""
            INSERT INTO purchase_orders (id, customer_id)
            VALUES (?, ?)
            """, orderId, customerId);

        jdbc.update("""
            INSERT INTO outbox_events
                (event_id, aggregate_id, topic_name, payload)
            VALUES (?, ?, ?, ?)
            """, eventId, orderId, "orders.created", eventJson);
    }
}
~~~

If inserting the outbox row fails, the database rolls back creating the order as well. If the commit succeeds, publish intent is durably stored alongside the order. `eventJson` should include `eventId`, `aggregateId`, `eventType`, `schemaVersion`, and domain payload matching the message contract—never expose arbitrary entity internals as public contracts.

This boundary is a **JDBC transaction**. In a Spring Data R2DBC service, the same outbox pattern applies, except both inserts must execute within **one reactive transaction** (e.g., `TransactionalOperator` with `R2dbcTransactionManager`). Never mix JDBC and R2DBC assuming they share a transaction merely because they target the same database.

### 7.3. Outbox Relay Sending Messages and Marking Sent

A periodic relay or Change Data Capture (CDC) tool reads unpublished outbox rows:

~~~java
// Illustrative relay logic; batch fetching/claiming omitted.
void publish(OutboxRow row) {
    kafkaTemplate
        .send(row.topicName(), row.aggregateId().toString(), row.payload())
        .join(); // Wait for broker confirmation; run on an appropriate worker.

    jdbcTemplate.update("""
        UPDATE outbox_events
           SET published_at = CURRENT_TIMESTAMP
         WHERE event_id = ?
           AND published_at IS NULL
        """, row.eventId());
}
~~~

`OutboxRow` is an application DTO. This snippet shows the **send-then-mark** sequence, not a full production relay ready to copy-paste. `KafkaTemplate.send(...)` in Spring Kafka 3.x+ returns `CompletableFuture`; calling `join()` blocks, so run it only on dedicated I/O workers/schedulers—never on a WebFlux event loop.

If the relay crashes **after Kafka confirms yet before updating `published_at`**, the same event is sent again. This is **expected** in the outbox pattern, so consumers must be idempotent. Conversely, marking sent before sending risks permanently losing events if Kafka fails.

With multiple relay replicas, coordinate row claims—using short transactions with `FOR UPDATE SKIP LOCKED`, timed leases, or CDC such as Debezium. Never hold SQL locks open while waiting on broker network calls if claim and publish can be decoupled. Include exponential backoff, attempt caps, backlog alerts, and poison-event handling.

The transactional outbox guarantees **business data and publish intent commit atomically in the database**. The relay provides *at-least-once delivery* to Kafka; it **does not** turn DB commit and Kafka publish into a single shared transaction.

## 8. Idempotent Consumer: Tolerating Redeliveries and Reprocessing

On the receiving side, Kafka can redeliver records after rebalances, crashes, timeouts, retries, or duplicate relay sends. If a consumer deducts inventory and crashes before committing its offset, the record returns on restart.

One strategy records processed event IDs in the **same database transaction** as the business mutation:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Processing steps in the receiving service:

1. Parse and validate the message contract, extracting the stable `eventId`.
2. Start a DB transaction.
3. Attempt `INSERT INTO processed_events(consumer_name, event_id) VALUES (?, ?) ON CONFLICT DO NOTHING` (PostgreSQL).
4. If **1** row was inserted, apply the business update in the **same DB transaction**; if **0**, treat it as already processed and skip side effects.
5. Commit the database; **only then** allow the listener container to commit/ack the offset per configured mode.

If the business update fails, the transaction rolls back `processed_events` as well so the next attempt can retry cleanly. If the DB commits and the offset does not, Kafka redelivers and `processed_events` prevents deducting inventory twice.

**Spring caveat:** if a `@KafkaListener` method carries database `@Transactional` AND calls `ack.acknowledge()` **inside the method**, the ack may execute before the transaction interceptor actually commits upon method exit. A cleaner pattern separates the listener from a **separate `@Transactional` service**, letting the service return (and commit) before the listener acks. If the listener container manages Kafka transactions, understand its exact offset-commit timing; never treat `ack()` as an atomic DB/Kafka commit.

In Spring Kafka, `@RetryableTopic`, dead-letter topics (DLTs), error handlers, and retry policies address error routing—they do not replace database idempotency. Distinguish transient errors (unavailable DB), permanent data errors (bad schema), and business rejections (declined order) to route retries and DLTs cleanly.

## 9. Selecting a Strategy by Integration Requirement

| Requirement | Suitable Design | What Remains to Handle |
|---|---|---|
| Atomically write multiple Kafka topics/partitions | Kafka producer transaction | `read_committed` consumers, aborts, instance fencing |
| Read Kafka, transform, write Kafka, commit input offset | Kafka transaction enlisting input offsets | Listener container config, retries, external sources |
| Write DB and ensure event has a path to Kafka | Transactional outbox + relay/CDC | Duplicate publishes, backlogs, multi-worker claims, idempotent consumer |
| Read Kafka and update database | DB transaction + `eventId` dedup, ack after DB commit | Crash replays, retries/DLT, offsets, ordering |
| Multiple services and databases in one workflow | Saga (orchestration/choreography) with compensations | Idempotency, timeouts, intermediate states, distributed tracing |
| Everything inside one database | Single DB transaction | Isolation, locking, deadlocks, consistency |

Simpler systems sometimes accept "write DB then publish directly and retry" when risk is low, provided they **explicitly accept** the post-commit event-loss window and provide reconciliation. For payments, inventory, shipping, or critical state sync, an outbox is usually worthwhile because it eliminates event loss at the source.

### Do Kafka Transactions Replace an Outbox?

No. Kafka transactions coordinate steps **internal to Kafka**; an outbox atomically persists **business state and publish intent** inside one DB transaction. Both address different boundaries and can even coexist depending on architecture.

### Should `@Transactional` Wrap the Entire Listener?

Only when you explicitly know **which transaction manager** it selects and **when offsets commit**. With multiple transaction managers, specify the bean name explicitly. One annotation never spans JDBC/JPA/R2DBC, Kafka, Redis, and HTTP in a single distributed transaction.

### Can Database Changes Achieve Exactly-Once?

You can achieve **exactly-once business effects** per `eventId` using unique constraints, recording processed IDs inside the same DB transaction, and safe reprocessing—even though message transport remains at-least-once. For side effects outside databases (sending emails, charging cards), enforce idempotency keys on the target, state machines, or reconciliation workflows.

## 10. Testing Transaction Boundaries

Use **Testcontainers PostgreSQL + Kafka** (or equivalent real integration infrastructure) to inject real faults and inspect actual offsets and committed rows, rather than mocking `KafkaTemplate` and repositories.

| Test Case | Fault / Trigger | Expected Outcome |
|---|---|---|
| Kafka tx commit | Write two outputs and commit | `read_committed` consumer reads both |
| Kafka tx abort | Write output then abort | `read_committed` consumer never sees aborted output |
| Kafka input offset | Process input and write output in tx, force abort | Input offset stays uncommitted in tx; record is re-read |
| DB rollback | Order insert succeeds, outbox insert fails | Both order and outbox roll back |
| Relay crash before send | Outbox row persisted, relay killed pre-publish | Row stays unpublished and retries on restart |
| Relay crash after Kafka ack | Kafka persisted record, DB still unmarked | Relay may republish; idempotent consumer prevents duplicates |
| Consumer crash after DB commit | DB updated, offset uncommitted | Rebalance/retry does not duplicate side effects |
| Concurrent duplicate `eventId` | Two consumers process same event against same DB | Unique constraint ensures only one DB tx applies side effects |
| Malformed schema | Missing required field or unsupported version | No bad DB writes; routed to DLT/quarantine per policy |
| Multiple relay replicas | Concurrent polling of outbox table | Claim/lease minimizes redundant sends; retries stay safe |

In `read_committed` tests, verify not only that committed records arrive, but also that aborted transactions stay **invisible** to the consumer. Consume-process-produce tests must assert **input offsets** too; checking only the output topic does not prove offsets participated in the Kafka transaction.

Never mock two commits and claim PostgreSQL and Kafka are atomic; inject faults right at real boundaries and prove recovery works.

## 11. Production Observability and Operations

To spot an integration flow stuck between DB and Kafka, monitor both sides together:

- **Database:** commit/rollback errors, deadlocks, timeouts, unpublished outbox row count, oldest unpublished row age, retry counts.
- **Kafka producer:** send errors, timeouts, transaction aborts, fencing errors, send/commit latency, retries, topic throughput.
- **Kafka consumer:** consumer lag, rebalance counts, deserialization/contract errors, retries, DLT counts, deduplicated duplicate rates.
- **Business flow:** `eventId`, `aggregateId`, `correlationId`/`traceId`, order state, and end-to-end DB-commit-to-Kafka-publish latency.

Emit structured logs with consistent identifiers across adapters while keeping sensitive payloads and secrets out of logs. Alert when **outbox backlog climbs steadily** or DLT messages sit unhandled—because the API request may have returned 200 while downstream never received the event.

Set realistic Kafka transaction timeouts, understand how Kafka fences old producers on restart, and choose `transaction-id-prefix` values that never collide across concurrent instances. Provision required ACLs on topics, consumer groups, and transactional IDs. Ensure outbox workers support graceful shutdown and backoff after broker outages.

## 12. Mistakes to Avoid

1. **"Adding `@Transactional` makes DB and Kafka roll back together."** False: identify the exact transaction manager and enlisted resources.
2. **"Kafka exactly-once guarantees consumers never update the DB twice."** False: external DBs sit outside Kafka transactions; enforce DB deduplication.
3. **"Enabling producer idempotence makes all business retries duplicate-free."** False: producer idempotence does not replace event IDs or business idempotency.
4. **"Kafka send succeeded means the consumer finished processing."** False: producer acks confirm broker writes per config; consumer handling and commits happen separately.
5. **"An outbox guarantees Kafka receives every event strictly once."** False: relays can republish after crashes; consumers must tolerate at-least-once delivery.
6. **"Acking offsets inside a database `@Transactional` method definitely happens after DB commit."** False if ack runs before the transaction interceptor commits on return.
7. **"Rolling back SQL after Kafka commits deletes the Kafka event."** False: both systems maintain separate logs and managers; design compensation/reconciliation.

## 13. Self-Check Questions

1. If DB commit succeeds and the process crashes right before `KafkaTemplate.send`, how does the system recover the event?
2. When a Kafka transaction aborts, how do `read_uncommitted` and `read_committed` consumers differ in what they observe?
3. To achieve exactly-once across a Kafka → Kafka flow, why must input offsets join the Kafka transaction?
4. Why can an outbox relay still send duplicates even though the order and outbox row committed atomically?
5. If a consumer deducts stock and crashes before committing its offset, what table/key prevents deducting twice?
6. When an app defines both `KafkaTransactionManager` and `JpaTransactionManager`, what must you specify before using `@Transactional`?
7. With multiple relay replicas running, how do you stop two instances from claiming the same row while still recovering if one dies?

**Key Takeaway:** Database transactions protect updates inside the database; Kafka transactions protect Kafka records and offsets enlisted in the same Kafka transaction. Coordinating both systems requires explicit messaging patterns, handling boundary failures, idempotency, and replay testing. When events must follow database commits, **transactional outbox + idempotent consumer** is far more reliable and verifiable than assuming one transaction spans both systems.

### References

- [Apache Kafka — Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once, and the scope of exactly-once.
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): `transactional.id`, `enable.idempotence`, `acks`, and related settings.
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTemplate`, listener container transactions, `KafkaTransactionManager`, and coordinating with other transaction managers.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction manager scope and `@Transactional` mechanics.
