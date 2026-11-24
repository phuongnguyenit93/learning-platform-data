# Outbox and Relay Process in Spring Framework Application Events

## 1. The problem: database write succeeds, but external event sending fails

In a Spring application, `ApplicationEventPublisher.publishEvent(...)` is useful for notifying components within the same `ApplicationContext` that an event has occurred. However, when the event needs to reach **another process/service** (such as billing, shipping, inventory, search indexing, or a notification system), merely calling the internal publisher or an HTTP client directly inside the use case **does not guarantee both systems see a consistent outcome**.

For example, an order placement use case has two actions:

1. Save the Order to the database.
2. Send `OrderPlaced` to a message broker or external service.

If done sequentially:

~~~text
Request
   |
   +--> BEGIN DB transaction
   +--> INSERT order
   +--> COMMIT DB
   |
   +--> broker.publish(OrderPlaced)
              |
              +--> network timeout / broker unavailable / process crash
~~~

The database has recorded the order, yet the event needed by another service **may never have been delivered**. Reversing the order does not solve it either:

~~~text
broker.publish(OrderPlaced) --> accepted
                   |
                   +--> INSERT order
                   +--> DB rollback
~~~

The outside world has heard an `OrderPlaced` fact even though the source order does not exist because the transaction rolled back.

This is the **dual-write problem**: the application is trying to write to two independent resources (database and broker), but a local database transaction does not span both. Merely adding `@Transactional` around an HTTP/broker publish does not turn a database transaction into a distributed transaction.

The **transactional outbox pattern** separates the two milestones:

- Within **one database transaction**, persist the business state **and** an outbox record describing the intent to deliver the event.
- A separate **relay process** reads committed outbox records, delivers them to the broker/external destination, tracks results, and retries when needed.

Diagram:

~~~text
OrderService
   |
   |  T1: one local DB transaction
   +-- INSERT orders
   +-- INSERT outbox(eventId, OrderPlaced, ...)
   +-- COMMIT T1
   |
   v
Order DB + Outbox Table
   |
   | Polling relay or CDC relay
   v
Message Broker / Integration Endpoint
   |
   v
Consumer
   +-- deduplicate eventId
   +-- update local state / side effect
   +-- acknowledge/checkpoint
~~~

**Core meaning:** The order and the **intent to deliver the event** commit together or roll back together. The relay performs network I/O **after the transaction**, capable of resuming from the durable record when the process restarts.

This lesson belongs to the **External Integration** group of Spring Framework Application Events. The focus is the database ↔ relay ↔ broker ↔ consumer boundary, not just how to invoke an event listener annotation.

## 2. Outbox guarantees: what it gives you and what it does not

The outbox solves a critical inconsistency:

- If the business transaction **rolls back**, the outbox record also rolls back.
- If the business transaction **commits**, the intent to send the event has a durable record in the same database.
- If the app or relay dies after commit, a properly operated relay can resume from pending/uncheckpointed records.

However, the outbox **does not automatically provide “exactly once delivery/effect”**. The relay can deliver **the same event multiple times**, especially when the broker accepts it but the relay dies before updating the sent status. Consumers need idempotency/deduplication.

### 2.1. Status milestones that must be distinguished

| Milestone | What can be asserted | What cannot yet be asserted |
| --- | --- | --- |
| Use case calls `INSERT outbox` | The DB is being asked to create the intent | The transaction has committed |
| Transaction commits | Business state and outbox intent coexist | The broker has received the event |
| Relay claims record | A worker took responsibility to attempt sending | It has been sent or acked |
| Broker confirms publish per contract | Broker accepted it per its guarantee level | Consumer has processed it |
| Consumer receives event | Message was delivered to consumer | Side effect has committed |
| Consumer commits + acks | Outcome recorded per consumer contract | No future redelivery will occur |
| Relay marks `SENT` | Relay recorded the publish ack | All downstream consumers finished |

Do not transition the outbox state to `SENT` right after merely **enqueuing a task in RAM** or before receiving the corresponding broker acknowledgment.

### 2.2. At-least-once or exactly-once?

Practical outbox designs usually target **at-least-once delivery**: events may be redelivered, but there must be a retry/recovery path so they are not silently lost. Specific policies also depend on retention, message TTL, broker acks, relay operations, and consumers.

“Exactly-once” at the broker layer (if a mechanism supports it) **does not mean** business effects on an external database/email/payment system will execute only once. You need idempotency keys, unique constraints, or consumer transactions to control side effects.

## 3. Components and responsibilities

### 3.1. Producer / transaction owner

The source application owns the aggregate, validation, and transaction boundary. It creates an event **after a valid business change**, and writes it to the outbox **in the same transaction** as the source data.

The producer does not wait for external services to finish processing; it commits that it has recorded the intent to deliver the event. If a business API needs to wait for downstream completion, a separate workflow/orchestration and status contract are required—do not assume the outbox itself is a synchronous RPC.

### 3.2. Outbox storage

A table or durable storage mechanism containing event ID, aggregate ID, event type, schema version, payload, timestamps, and delivery status (if using polling). The outbox is written using the same `DataSource`/local transaction manager as the business state. **Do not use two independent databases and assume both commit together.**

### 3.3. Relay process

A relay can be:

- A scheduled/polling worker within the same codebase but with its own lifecycle and capacity.
- An independent service/job runner reading the outbox table.
- A **CDC (Change Data Capture)** connector reading the database commit log, such as Debezium, and forwarding outbox inserts to the broker.

Regardless of which process hosts it, the relay must be restartable, bound in-flight work, and track errors/lag.

### 3.4. Broker and consumer

The broker (Kafka, RabbitMQ, managed queue, etc.) is responsible for storing/routing messages according to its configuration. The consumer processes the event on the receiving side, with its own transaction and checkpoint/ack. The consumer **must not assume a message appears only once** just because the source uses an outbox.

## 4. Designing an outbox table for a polling relay

A PostgreSQL example illustrating a **polling relay that updates status**:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    total_cents BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    correlation_id VARCHAR(100),
    state VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ,
    last_error_code VARCHAR(100)
);

CREATE INDEX idx_outbox_ready
    ON outbox (state, available_at, created_at, event_id);

CREATE INDEX idx_outbox_aggregate
    ON outbox (aggregate_type, aggregate_id, aggregate_version);
~~~

**This is an illustrative PostgreSQL schema**, not a universal SQL schema for every database. Indexes, partitioning, retention, and isolation levels should be reviewed with a DBA for actual load.

An event:

~~~json
{
  "eventId": "11111111-1111-4111-8111-111111111111",
  "aggregateType": "Order",
  "aggregateId": "101",
  "aggregateVersion": 7,
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T04:00:00Z",
  "payload": {
    "orderId": 101,
    "totalCents": 8500
  }
}
~~~

Fields to consider:

| Field | Purpose | Notes |
| --- | --- | --- |
| `event_id` | Stable identity for dedup | Unique and unchanged across retries |
| `aggregate_type`/`aggregate_id` | Route/partition same aggregate | Do not put PII into keys arbitrarily |
| `aggregate_version` | Check ordering, stale events | Incremented per domain rules |
| `event_type`/`schema_version` | Consumer contract | Supports schema evolution |
| `payload` | Minimal fact data | Do not serialize raw JPA entities |
| `correlation_id` | Links request/workflow | Avoid secrets in correlation ID |
| `state` | Polling relay status | `PENDING`/`IN_FLIGHT`/`SENT`/`FAILED` |
| `attempts`/`available_at` | Retries and backoff | Avoid infinite retries |
| `lease_owner`/`lease_until` | Claiming across multiple relay workers | Needs token/fencing for late updates |
| `created_at`/`sent_at` | Measure backlog/lag | Use clear UTC timestamps |
| `last_error_code` | Diagnostics | Do not write raw payload/secrets into errors |

### 4.1. Do not use a mutable polling table for every kind of CDC

A schema with `state`, `attempts`, and `UPDATE` statements belongs to a **polling relay design**. With CDC using the default Debezium Outbox Event Router SMT, the model is typically **append-only INSERTs into the outbox** so the connector reads the database log; the default SMT configuration expects insert outbox change events and **does not treat state updates as new event signals**.

Therefore, clearly separate the **two operational models**:

- **Polling relay:** application/worker updates `PENDING` → `IN_FLIGHT` → `SENT` to manage the queue.
- **CDC outbox:** application writes append-only outbox rows; the connector forwards inserted records based on the change log/offset. Separate cleanup/retention/checkpoint policies apply; do not blindly port every polling state transition onto the default SMT.

Do not mix both mechanisms haphazardly on the same table and expect every update to produce a valid message.

## 5. Proper transactions in Spring: writing business state and outbox in the same commit

In Spring, a `@Transactional` service can use `JdbcTemplate`/JPA repositories to write business state and the outbox. The condition is **sharing the same transaction manager and corresponding database connection/resource**.

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void place(PlaceOrder command) {
        Order order = validateAndCreate(command);
        orders.save(order);
        outbox.insert(
            OrderPlaced.from(order)
        );
    }
}
~~~

This is **illustrative code in an application with undefined types/repositories**, not a standalone compilable file. A runnable example with Spring JDBC/H2 is in section 11.

### 5.1. “Same transaction” is the core requirement

Do not separate:

~~~text
T1: save order in DB-A   -> COMMIT
T2: save outbox in DB-B  -> COMMIT
~~~

and call that a transactional outbox with atomic guarantees. A failure window remains between T1 and T2. Even within the same RDBMS, using independent connections/transaction managers can break atomicity.

If the source service already has a database, the outbox is normally stored **in that same database and local transaction**; the relay then handles delivering messages externally.

### 5.2. Proxy-based @Transactional and self-invocation

Proxy-based Spring `@Transactional` only intercepts calls passing through the bean proxy. An internal `this.place(...)` call on the same object typically **does not open a new transaction** per the annotation on the self-invoked method. Therefore, invoke transactional services through the Spring bean, test actual rollbacks, and do not instantiate services manually with `new` expecting `@Transactional` to take effect.

By default, Spring rolls back when a transactional method throws a `RuntimeException` or `Error`; checked exceptions have different default rules and can be configured. In the demo, the simulated error is `IllegalStateException`, so the transaction rolls back both order and outbox.

### 5.3. Do not call the broker inside the same DB transaction and assume it is atomic

~~~java
@Transactional
public void placeOrder(...) {
    orders.save(...);
    broker.publish(...);
}
~~~

Even if `broker.publish` is called before commit, **a DB transaction does not automatically roll back a message already accepted by the broker**. And if the DB commits before publishing, the app can die before the send. The outbox moves the network call outside the transaction, eliminating this mismatch risk.

## 6. Polling relay: from claiming to broker acknowledgment

A polling relay needs to do more than “SELECT pending rows and send” when there are multiple instances or high traffic.

A production cycle typically consists of:

1. Select a batch of records with `state=PENDING` and `available_at <= now()`, or whose previous lease expired.
2. **Claim atomically** so only one worker owns the right to attempt delivery during the lease window.
3. Commit the claim transaction **before doing network I/O** (avoid holding row locks for the duration of the broker call).
4. Publish to the broker, waiting for **ack per the broker contract** (not just in-RAM enqueue).
5. Upon successful ack, write `SENT` conditioned on the owner/token still being valid.
6. On transient error, record retry state and a new `available_at`, incrementing `attempts`.
7. On permanent/max-attempts error, transition to `FAILED`/quarantine, alert, and provide a reprocessing procedure.
8. When a worker dies, lease expiration allows another worker to retry the record.

~~~text
PENDING
   |
   | claim with lease/fencing
   v
IN_FLIGHT
   |
   +-- ack received --> SENT
   |
   +-- transient failure --> PENDING (available_at future)
   |
   +-- permanent failure --> FAILED / quarantine
   |
   +-- worker crash --> lease expires --> retry/reclaim
~~~

### 6.1. Claiming sketch on PostgreSQL

~~~sql
-- PostgreSQL SQL pseudocode; very short transaction.
BEGIN;

SELECT event_id
FROM outbox
WHERE (state = 'PENDING' AND available_at <= now())
   OR (state = 'IN_FLIGHT' AND lease_until < now())
ORDER BY created_at, event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- For the locked set of event_ids, update:
-- state = 'IN_FLIGHT'
-- lease_owner = worker identity
-- lease_until = now() + lease duration
-- attempts = attempts + 1
-- claim_token = fresh unique token (if schema has this column)
-- Then COMMIT before calling the broker.

COMMIT;
~~~

This is an **explanation of the mechanism**, not a self-running stored procedure: the application must receive the set of IDs, execute the `UPDATE` on the exact claimed rows, and commit. How `FOR UPDATE SKIP LOCKED`/isolation behaves depends on the RDBMS and version. If `claim_token` is needed, add the column and unique token rules in the production schema.

**Do not hold a transaction/row lock throughout `broker.send()`** because the network can be slow or time out, stalling the DB. The worker only needs a short claim and then delivers outside the claim transaction.

### 6.2. Lease, fencing, and races

Suppose worker A claims an event, hangs for a long time, and the lease expires. Worker B reclaims it, sends successfully, and then A wakes up and tries to update `SENT` or `FAILED`. Without a **fencing token/claim generation**, A’s late update could overwrite B’s valid state.

An update should require both the event ID **and** the current claim token, for example:

~~~sql
UPDATE outbox
SET state = 'SENT', sent_at = now()
WHERE event_id = :eventId
  AND state = 'IN_FLIGHT'
  AND claim_token = :claimToken;
~~~

This is **illustrative SQL with named parameters**. Use it only when the schema includes `claim_token`, and always check the affected row count. A token prevents a stale worker from mutating state, **but cannot prevent a message from having already been sent twice**; consumers still need idempotency.

### 6.3. Polling frequency and batch size

Polling too frequently can cause continuous DB scanning; polling too slowly increases event lag. Choose batch size, indexes, worker concurrency, jitter, and sleep/backoff based on `oldest_pending_age`, query latency, and throughput metrics.

Do not rely solely on `Thread.sleep(100)` in an infinite loop. You can use `@Scheduled(fixedDelayString=...)`, a job runner, or a dedicated relay service with proper lifecycle, cancellation, bounded concurrency, and graceful shutdown. When running multiple instances, claim/lease coordination is mandatory.

## 7. Failure windows: why do retries cause duplicates while still being right by design?

Consider the milestones:

~~~text
A. DB commits order + outbox
B. Relay reads and claims
C. Relay publishes event to broker
D. Broker confirms acceptance
E. Relay writes SENT to DB
F. Consumer processes/acks
~~~

Failure points:

| Failure occurs at | Situation | Recovery strategy |
| --- | --- | --- |
| Before A | Transaction can roll back, no committed intent | Request retry per contract |
| After A, before B | Outbox row remains pending | Relay reads again after restart |
| Between B and C | Record is leased but not yet sent | Lease expires, retry |
| After C/D, before E | Broker **may have received it**, outbox still not `SENT` | Relay sends again; consumer deduplicates |
| After E, before F | Relay considers broker received it, consumer may not be done | Broker retention/ack/consumer retries |
| During F before consumer commit | Consumer may receive message again | Transactional inbox + idempotency |
| After consumer commit, before ack | Side effect may be done, yet message is redelivered | Deduplicate by stable event ID |

**The D → E window is the most important one for understanding at-least-once:** the relay delivered successfully but died before updating the outbox. After restart, resending the same event is **expected behavior that the system must be designed to tolerate**.

Do not set `SENT` **before** the broker actually confirms per the desired guarantee level: doing so opens a window where an event is marked complete without ever reaching the broker.

### 7.1. Broker ack differs from consumer ack

Kafka producer acknowledgments, RabbitMQ publisher confirms, or managed queue send acknowledgments are **broker-layer confirmations** under specific configurations. They do not prove every subscriber executed its business side effects. Consumer processing and checkpoint/ack form a separate chain of responsibility.

Monitoring must therefore distinguish **outbox pending lag**, **relay publish success**, **broker queue/consumer lag**, and **consumer outcomes**.

## 8. Polling relay or CDC (Change Data Capture)?

Both approaches use an outbox, but their tooling, permissions, and operational models differ.

| Criterion | Polling relay | CDC relay (e.g., Debezium) |
| --- | --- | --- |
| Read source | Query outbox table | Database commit/change log |
| Processing state | Typically `PENDING`/`LEASE`/`SENT` | Connector offset/checkpoint, per SMT |
| Load on DB | Batched `SELECT`/`UPDATE` | Log streaming; still has operational overhead |
| Latency | Depends on poll interval, batch, DB | Can be low; depends on connector/broker |
| Multiple workers | Claim/lock/lease | Connector task/partition semantics |
| Operations | App implements relay and cleanup | Connector, log retention, snapshots, config |
| Portability | SQL per DB | Depends on connector/CDC support |
| Failure handling | App owns retry/lease | Connector framework + broker + consumer |
| Ordering | Must design claiming/sequence | Commit order/partition key depending on pipeline |
| Best suited for | Small–medium systems, simpler infra | High-volume change streaming with existing CDC infra |

### 8.1. Debezium Outbox Event Router

Debezium provides an **Outbox Event Router SMT** that can transform an outbox row insert into a Kafka message. Default fields in the Debezium documentation include `id`, `aggregatetype`, `aggregateid`, `type`, and `payload`.

Conceptual example:

~~~text
outbox INSERT:
  id = evt-123
  aggregatetype = Order
  aggregateid = 101
  type = OrderPlaced
  payload = {orderId:101,totalCents:8500}

Debezium connector + Outbox Event Router
  |
  +--> topic like outbox.event.Order
  +--> key is aggregateid
  +--> message body from payload
  +--> event ID used in header/metadata per config
~~~

**Note:** this is a high-level description, not a complete Debezium configuration file. With the default SMT, the outbox is expected to generate inserts with appropriate filtering of deletes/updates. Do not assume the mutable `PENDING`/`SENT` polling schema above will be processed identically by the SMT.

`aggregateid` is commonly used as the Kafka key so events for the same aggregate go to the same partition when partitioning is stable, supporting per-key ordering. However, **end-to-end processing order** still depends on retries, consumer concurrency, and whether version/sequence guards are used.

### 8.2. Responsibilities CDC does not eliminate

- Monitoring connector health, offset lag, database log retention, and snapshot behavior.
- Ensuring outbox `INSERT`s match the mapping schema/payload.
- Checking topic/key mapping, `eventId` header, and `schemaVersion`.
- Implementing idempotent consumers.
- Managing migrations, cleanup, and retention of outbox/CDC logs.
- Protecting data in commit logs, connectors, brokers, and consumers.
- Testing restarts, connector rebalancing, duplicate delivery, and replays.

CDC changes the relay mechanism; **it does not remove the need to design message contracts and consumer recovery**.

## 9. Ordering: commit order, send order, and processing order can differ

Suppose the same Order 101 has:

~~~text
OrderPlaced      version=1
OrderConfirmed   version=2
OrderShipped     version=3
~~~

If two relay workers claim these three records and send concurrently, the broker or consumer may observe a different order. To preserve the state machine:

- Record `aggregate_id` and `aggregate_version` at the moment the fact is created.
- Increment the version inside the **transaction updating the aggregate**.
- Route by `aggregate_id` key to keep the same partition/ordering where the broker supports it.
- Avoid concurrent processing for the same aggregate in the consumer when strict ordering is required.
- Have the consumer check the version; do not apply a stale event if the aggregate is already at a newer version.
- Define a policy for missing versions (buffer, retry, fetch state, reconcile) rather than skipping unconditionally.

### 9.1. Do not treat created_at as an exact sequence

Two rows can share the same timestamp, and clocks across multiple processes can skew. `ORDER BY created_at` is useful for polling but does not guarantee the **logical order** of all events. You need explicit version/sequence numbers or well-defined commit/partition ordering.

### 9.2. Transactions producing multiple events for the same aggregate

If a single transaction mutates an aggregate and produces multiple events, rules for versioning and event ordering must be defined. Never reuse the same `eventId` for two distinct facts; an event ID is the identity of **each individual event instance**.

## 10. Idempotent consumer: transactional inbox and side effects

A consumer may receive the same event multiple times. The **inbox/dedup table** pattern uses a unique key:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside the consumer’s transaction:

~~~text
BEGIN consumer transaction
  INSERT (consumerName, eventId) into inbox with unique constraint
  IF duplicate:
      treat as already processed, do not repeat DB side effect
  ELSE:
      apply state change/business effect
COMMIT consumer transaction
ACK message after commit
~~~

**Critical condition:** the inbox insert and **local database side effect** must be in the same transaction to guarantee atomic deduplication for that data. If the inbox commits first and then the DB side effect fails, retries may wrongly skip it.

### 10.1. External side effects are more complex

If a consumer calls an email service, payment API, or external service, the inbox’s DB transaction **cannot roll back the external call**. You need an API idempotency key if supported, a consumer-side command intent/outbox model, or a workflow with reconciliation.

For instance, if an email was sent and the response timed out, retrying with the same event ID may send a duplicate if the provider lacks idempotency and the system does not track outcomes properly. Do not promise “exactly once email” simply because an inbox table exists.

### 10.2. Identity must remain stable

`eventId` must stay identical across relay retries, broker redeliveries, or consumer retries of the same fact. Generating a new UUID on each resend defeats deduplication. Conversely, two distinct events—even for the same order ID—must never share an `eventId`.

## 11. Complete Java 17+ project: atomic outbox, relay, and redelivery

The following example **runs standalone** with Java 17+, Maven, Spring Framework 6.2.8, Spring JDBC, and in-memory H2. No Spring Boot, Kafka, or external database server is required.

Goals:

1. `OrderService.place(...)` saves an Order + outbox row in the same **Spring-managed transaction**.
2. A call throwing `IllegalStateException` after attempting both inserts rolls back: **neither the Order nor the outbox row from the failed request remains**.
3. The relay reads the pending outbox and forwards to `FakeBroker`.
4. The relay intentionally simulates a **crash after broker acceptance but before marking `SENT`**, leaving the outbox row pending.
5. The relay runs again, resending the same event ID; the consumer uses a **transactional inbox** and unique constraint to avoid recording the database side effect a second time.
6. The relay marks `SENT` after the second simulated publish/ack.

**Exact limitations of the example:** `FakeBroker` invokes the consumer synchronously in the same JVM to simulate the send/receive path; it **does not** simulate the durability and acknowledgment modes of real Kafka/RabbitMQ. H2 is also an in-memory database and therefore **does not survive a process restart**. The “crash” is simulated by returning before updating `SENT` without killing the process. The demo verifies transaction/redelivery logic, **not proof of durable delivery across real process kills**.

### 11.1. File structure

~~~text
spring-outbox-relay-demo/
├── pom.xml
└── src/main/java/OutboxRelayDemo.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-outbox-relay-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>OutboxRelayDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. src/main/java/OutboxRelayDemo.java

~~~java
import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class OutboxRelayDemo {

    public record OutboxRow(
        String eventId, long orderId, String payload
    ) { }

    // Not final: Spring creates a transaction proxy for the service.
    public static class OrderService {
        private final JdbcTemplate jdbc;

        public OrderService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void place(
                long id, long totalCents,
                String eventId, boolean simulateFailure
        ) {
            if (id <= 0 || totalCents <= 0) {
                throw new IllegalArgumentException("invalid order");
            }

            jdbc.update(
                "INSERT INTO orders(id, total_cents) VALUES (?, ?)",
                id, totalCents
            );

            jdbc.update(
                "INSERT INTO outbox(" +
                "event_id, order_id, event_type, payload, status" +
                ") VALUES (?, ?, ?, ?, 'PENDING')",
                eventId,
                id,
                "OrderPlaced",
                "orderId=" + id + ";totalCents=" + totalCents
            );

            if (simulateFailure) {
                throw new IllegalStateException("forced rollback");
            }
        }
    }

    // Local side effect and inbox are written atomically.
    public static class InboxConsumer {
        private final JdbcTemplate jdbc;

        public InboxConsumer(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void consume(OutboxRow row) {
            jdbc.update(
                "INSERT INTO consumer_inbox(event_id) VALUES (?)",
                row.eventId()
            );

            jdbc.update(
                "INSERT INTO notification_effects(" +
                "event_id, order_id) VALUES (?, ?)",
                row.eventId(),
                row.orderId()
            );
        }
    }

    // Simulates the broker receiving + dispatching to the consumer.
    public static class FakeBroker {
        private final InboxConsumer consumer;

        public FakeBroker(InboxConsumer consumer) {
            this.consumer = consumer;
        }

        public void publish(OutboxRow row) {
            System.out.println("BROKER_ACCEPTED " + row.eventId());

            try {
                consumer.consume(row);
                System.out.println(
                    "CONSUMER_APPLIED " + row.eventId()
                );
            } catch (DuplicateKeyException ex) {
                // Unique constraint in consumer_inbox:
                // DB side effect was already processed on a prior delivery.
                System.out.println(
                    "CONSUMER_DUPLICATE " + row.eventId()
                );
            }
        }
    }

    // Single-worker polling relay, without multi-instance claim/lease yet.
    public static class Relay {
        private final JdbcTemplate jdbc;
        private final FakeBroker broker;

        public Relay(JdbcTemplate jdbc, FakeBroker broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public void tick(boolean crashBeforeMarkSent) {
            List<OutboxRow> pending = jdbc.query(
                "SELECT event_id, order_id, payload " +
                "FROM outbox WHERE status = 'PENDING' " +
                "ORDER BY event_id",
                (rs, n) -> new OutboxRow(
                    rs.getString("event_id"),
                    rs.getLong("order_id"),
                    rs.getString("payload")
                )
            );

            for (OutboxRow row : pending) {
                broker.publish(row);

                if (crashBeforeMarkSent) {
                    System.out.println(
                        "SIMULATED_CRASH_BEFORE_MARK " +
                        row.eventId()
                    );
                    return;
                }

                int changed = jdbc.update(
                    "UPDATE outbox SET status = 'SENT' " +
                    "WHERE event_id = ? AND status = 'PENDING'",
                    row.eventId()
                );

                if (changed != 1) {
                    throw new IllegalStateException(
                        "Unable to mark sent"
                    );
                }

                System.out.println(
                    "RELAY_MARKED_SENT " + row.eventId()
                );
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds =
                new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:outboxdemo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc) {
            return new OrderService(jdbc);
        }

        @Bean
        InboxConsumer inboxConsumer(JdbcTemplate jdbc) {
            return new InboxConsumer(jdbc);
        }

        @Bean
        FakeBroker fakeBroker(InboxConsumer consumer) {
            return new FakeBroker(consumer);
        }

        @Bean
        Relay relay(JdbcTemplate jdbc, FakeBroker broker) {
            return new Relay(jdbc, broker);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id BIGINT PRIMARY KEY, total_cents BIGINT NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE outbox (" +
                "event_id VARCHAR(80) PRIMARY KEY, " +
                "order_id BIGINT NOT NULL, " +
                "event_type VARCHAR(80) NOT NULL, " +
                "payload VARCHAR(200) NOT NULL, " +
                "status VARCHAR(15) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE consumer_inbox (" +
                "event_id VARCHAR(80) PRIMARY KEY)"
            );
            jdbc.execute(
                "CREATE TABLE notification_effects (" +
                "event_id VARCHAR(80) PRIMARY KEY, " +
                "order_id BIGINT NOT NULL)"
            );

            OrderService orders = context.getBean(
                OrderService.class
            );

            orders.place(101L, 8500L, "evt-101", false);

            try {
                // Both order and outbox INSERTs are executed,
                // but the exception rolls back the transaction.
                orders.place(102L, 9900L, "evt-102", true);
            } catch (IllegalStateException ex) {
                System.out.println("ROLLBACK_CONFIRMED");
            }

            System.out.println(
                "ORDERS=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders", Integer.class
                )
            );

            System.out.println(
                "OUTBOX_PENDING=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox " +
                    "WHERE status = 'PENDING'",
                    Integer.class
                )
            );

            Relay relay = context.getBean(Relay.class);

            // Delivered to FakeBroker/consumer but SENT status
            // not yet written: simulates the crash window.
            relay.tick(true);

            System.out.println(
                "PENDING_AFTER_SIMULATED_CRASH=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox " +
                    "WHERE status = 'PENDING'",
                    Integer.class
                )
            );

            // Redeliver old event: unique inbox prevents
            // repeating the DB side effect in the consumer.
            relay.tick(false);

            System.out.println(
                "OUTBOX_SENT=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox " +
                    "WHERE status = 'SENT'",
                    Integer.class
                )
            );

            System.out.println(
                "NOTIFICATION_EFFECTS=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM notification_effects",
                    Integer.class
                )
            );
        }
    }
}
~~~

### 11.4. Running and expected output

Inside the `spring-outbox-relay-demo` directory, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

The lines **printed by the program** when no configuration/dependency errors occur:

~~~text
ROLLBACK_CONFIRMED
ORDERS=1
OUTBOX_PENDING=1
BROKER_ACCEPTED evt-101
CONSUMER_APPLIED evt-101
SIMULATED_CRASH_BEFORE_MARK evt-101
PENDING_AFTER_SIMULATED_CRASH=1
BROKER_ACCEPTED evt-101
CONSUMER_DUPLICATE evt-101
RELAY_MARKED_SENT evt-101
OUTBOX_SENT=1
NOTIFICATION_EFFECTS=1
~~~

### 11.5. Output analysis

**Rollback verified by the DB:** calling `place(102, ..., true)` inserts the order/outbox and then throws `IllegalStateException`. Because `OrderService` comes from the Spring context and `@EnableTransactionManagement` is active, the transaction proxy coordinates the rollback. Subsequent queries show `ORDERS=1` and `OUTBOX_PENDING=1`: only order 101 and its event exist.

**First relay run:** reads pending `evt-101`, calls `FakeBroker.publish`, and the consumer writes `consumer_inbox` and `notification_effects` in one transaction and prints `CONSUMER_APPLIED`. The relay intentionally skips `UPDATE status='SENT'`, so it prints `SIMULATED_CRASH_BEFORE_MARK` and the row remains pending.

**Second relay run:** reads `evt-101` again and republishes. The duplicate insert on `consumer_inbox.event_id` violates the primary key, Spring JDBC throws `DuplicateKeyException`, the consumer’s transaction rolls back, and no second side effect is created. `FakeBroker` prints `CONSUMER_DUPLICATE`. The relay marks `SENT`, and finally `NOTIFICATION_EFFECTS=1`.

**Do not over-extrapolate:** deduplication here applies to **the consumer’s database side effect**. If `notification_effects` were replaced with an email/network call, you would need a separate idempotency strategy and uncertain-outcome handling. And in the H2 example, the fake broker does not run in a separate process; production must identify the exact broker ack milestone.

### 11.6. Why use JdbcTemplate instead of ApplicationEventPublisher?

The example requires **transaction operations and durable outbox persistence**, so it uses `JdbcTemplate` under `DataSourceTransactionManager` to clearly show two rows committing/rolling back together. `ApplicationEventPublisher` can still be used in-process for best-effort work; it **does not** automatically make payloads appear in the outbox table.

An architecture can combine both:

~~~text
OrderService transaction
   +--> orders table
   +--> outbox table       [external integration contract]

Optional after-commit internal event
   +--> in-process metrics/cache listeners (best effort)
~~~

Do not use an async `@EventListener` to write the outbox **after** commit and call that a transactional outbox: if the process dies before the listener writes, the intent can be lost. The outbox should be written **in the same source transaction**, through an explicitly invoked service/repository.

## 12. Comparing @EventListener, @TransactionalEventListener, and outbox

| Option | When it runs | Guarantees intent saved after crash? | Limitations |
| --- | --- | --- | --- |
| Sync `@EventListener` | When event is dispatched in context | No | Bound to thread/transaction, does not cross processes |
| `@Async @EventListener` | When executor runs task | No | RAM queue, async errors, process crashes |
| `@TransactionalEventListener(AFTER_COMMIT)` | After matching transaction commits | No | Right phase, but gap exists between commit → worker |
| Write outbox in `@Transactional` | Intent and domain state commit together | **Yes, per DB durability** | Not yet delivered to broker, requires relay |
| Polling relay | After outbox committed | Per DB + retry/lease design | Prone to duplicates, requires claiming/monitoring |
| CDC relay | Reads database log/offset | Per connector/retention/ack setup | Requires operating CDC and broker |
| Broker + idempotent consumer | After message reaches consumer | Per broker/consumer storage | Requires dedup and end-to-end error handling |

### 12.1. AFTER_COMMIT does not replace an outbox

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` only coordinates **when the listener can execute** after commit. If the process crashes after DB commit but before the listener/broker publish, the event can still be lost if no durable intent exists.

If published outside a transaction, `@TransactionalEventListener` may not run by default unless `fallbackExecution=true` is configured. This is specific to transaction-bound listeners, not a durability mechanism.

### 12.2. @Async does not share the source transaction

An `@Async` worker runs on a different thread and does not automatically inherit the publisher’s imperative thread-bound transaction. A worker writing the outbox in a separate transaction **after** commit leaves an intent-loss window. If a job truly must exist, write the outbox in the source transaction first.

### 12.3. Why not dual-write with “retry at the controller”?

If saving to the DB succeeds and sending to the broker fails, the API might return an error so the client retries the whole request. That can create a second order, duplicate payment, or ambiguous state. Idempotency on HTTP commands is helpful, yet it still **does not guarantee the event was durably recorded** if the outbound send lacks an outbox.

## 13. The relay process as a production service

A production relay typically includes:

- **Clear owner/lifecycle:** a dedicated scheduled worker, service, or CDC connector.
- **Batching and rate limiting:** bound the number of claimed rows and concurrent sends to avoid flooding the broker.
- **Lease/fencing:** multiple instances can cooperate without overwriting stale state.
- **Retries:** exponential backoff + jitter, classifying transient vs. permanent errors.
- **Ack-aware updates:** never mark `SENT` before confirmed broker publish.
- **Dead-letter/quarantine:** permanent schema/payload errors requiring human intervention or data repair.
- **Outbox cleanup:** retention for `SENT` rows; never delete unprocessed pending rows.
- **Alerting:** oldest pending age, failed total, lease expirations, backlog.
- **Graceful shutdown:** stop new claims, wait for in-flight sends within budget, release claims/let leases expire.
- **Operational replay:** a controlled way to retry selected events with the same event ID and an audit trail.

### 13.1. Scheduling with Spring

Example in a Spring application configured with `@EnableScheduling`:

~~~java
@Component
public class RelayScheduler {
    private final RelayService relay;

    public RelayScheduler(RelayService relay) {
        this.relay = relay;
    }

    @Scheduled(fixedDelayString = "PT1S")
    public void runCycle() {
        relay.claimAndDispatchBatch();
    }
}
~~~

This is an **illustrative snippet**: it requires annotation imports, a real `RelayService`, error handling, and ensuring two cycles do not overlap unintentionally. The value `PT1S` (duration string) is an example schedule, not an optimal policy. In multi-instance deployments, `@Scheduled` runs on every enabled instance; claim locks/leases remain mandatory.

### 13.2. Optimizing the relay without losing data

Backpressure may slow down or pause the relay, yet the outbox backlog remains stored in the DB. If storage grows unbounded or lacks capacity planning, the DB can fill up and affect business transactions. Therefore monitor **oldest pending**, table size, insert/send rates, index health, and purge delivered rows according to policy.

### 13.3. When to separate processes?

Separating the relay from the request service helps when broker I/O is resource-intensive, independent scaling/rollouts are needed, or you want a dedicated delivery-only process. However, a relay co-located in the application can still use an outbox properly if storage is durable and startup/shutdown are controlled. **The term “relay process” does not mandate a separate executable**, though separating deployments is often convenient under heavy load.

## 14. Event contracts, schema evolution, and data protection

An outbox row can outlive the release that created it. A consumer may process an event after code/schemas change. Therefore contracts need:

- Clear `eventType` and `schemaVersion`, with a backward-compatibility policy.
- Stable `eventId`, `aggregateId`, and `aggregateVersion` if ordering is required.
- Payloads independent of raw JPA entities or internal Java class names.
- Serializer/deserializer policies for older/newer consumers reading different versions.
- Migrations before adding required fields or changing field meanings.
- Explicit retention and cleanup; do not delete rows still needed for retries or CDC reads.

### 14.1. Do not over-serialize PII

Outboxes increase durability, so sensitive events may persist for a long time across DBs, backups, change logs, brokers, and consumer logs. Include only necessary data, encrypt at rest/in transit per policy, control DB/connector permissions, manage secrets, and enforce retention and data deletion requirements.

Do not put access tokens, passwords, raw HTTP requests, full `Authentication` objects, or JPA entities with association graphs into payloads just because they happen to be in scope at publish time.

### 14.2. Event ID and correlation ID

`eventId` is for deduplicating a fact. `correlationId` links a workflow; `causationId` can point to the event/command that caused the current event. These two trace fields **do not replace idempotency keys**, nor are they suitable as high-cardinality Prometheus labels.

## 15. Observability: measuring real backlog and latency

An outbox pipeline has multiple success/failure points:

~~~text
source committed -> outbox pending -> claimed -> broker accepted
    -> consumer received -> consumer DB committed -> consumer ack
~~~

Measure separately:

- `outbox_created_total`, `outbox_pending_count`, `outbox_oldest_pending_age_seconds`.
- `relay_claimed_total`, `relay_publish_success_total`, `relay_publish_failed_total`.
- `relay_retry_total`, `relay_lease_expired_total`, `relay_failed_or_quarantined_total`.
- `relay_publish_duration_seconds` and `outbox_delivery_lag_seconds`.
- Broker queue depth/consumer lag per the technology in use.
- `consumer_processed_total`, `consumer_duplicate_total`, `consumer_failure_total`.
- `inbox_commit_latency` and downstream side-effect outcomes.
- DB outbox table size, write latency, read query latency, disk/storage headroom.

The names above are **suggested application-defined metrics**, not defaults provided by Spring.

### 15.1. Metrics and logs must not leak data

High-cardinality `eventId`, `orderId`, emails, or tenant IDs belong in **controlled structured logs/traces**, not unbounded metric labels. Error codes should be bounded; do not copy raw exception messages containing PII into metric labels.

Purposeful log example:

~~~text
stage=outbox_insert eventType=OrderPlaced eventId=evt-101 status=committed
stage=relay_send eventId=evt-101 attempt=1 status=acked
stage=relay_recover eventId=evt-101 attempt=2 status=redelivered
stage=consumer eventId=evt-101 status=duplicate_skipped
~~~

These lines are an illustrative format only, not logs automatically produced by the demo in section 11.

### 15.2. Setting appropriate SLOs

Examples of SLOs to align with the business:

- 99.9% of outbox rows accepted by the broker within 30 seconds of commit.
- Oldest pending age rarely exceeds a few minutes.
- No rows stuck pending permanently without alerting.
- Consumer processing lag and duplicate counts are measured.
- Retries/failures/quarantine have runbooks and owners.

**These numbers are examples only, not fixed recommendations.** Latency targets for billing, email, and analytics can differ considerably.

## 16. Common implementation mistakes

1. **Writing Order and then publishing to the broker outside the transaction with no outbox:** dual-write gap causes lost events.
2. **Publishing to the broker before commit:** consumers may observe a fact even if the DB rolls back.
3. **Writing the outbox using a different database/transaction than the Order:** no longer atomic.
4. **Putting `INSERT outbox` in an `@Async` listener after commit:** a process crash can lose the intent.
5. **Treating `@TransactionalEventListener(AFTER_COMMIT)` as a durable queue:** it only coordinates phase timing.
6. **Marking `SENT` before getting a broker ack:** events are lost if the broker never received them.
7. **Assuming a broker ack proves consumer side effects committed:** two separate milestones.
8. **Lacking a stable `eventId`:** retries generate new UUIDs, breaking deduplication.
9. **Equating at-least-once with exactly-once:** duplicates are a normal occurrence.
10. **Consumer inbox insert and DB effect not in the same transaction:** can wrongly skip or repeat effects.
11. **Using a DB inbox to promise exactly-once external emails:** does not solve uncertainty in external APIs.
12. **Multiple relays polling the same records without atomic claiming:** unintended duplicate sends.
13. **Holding a DB lock across network sends:** increases contention, deadlocks, and transaction duration.
14. **Lease expiration without fencing tokens:** a stale worker overwrites the newer worker’s state.
15. **Relying on `created_at` for absolute ordering:** timestamps are not an aggregate sequence.
16. **Unbounded batch/retry sizes:** an overloaded relay degrades both DB and broker.
17. **No backoff/quarantine:** malformed payloads keep resending indefinitely.
18. **Deleting outbox rows before the connector reads them:** CDC loses data.
19. **Mixing a mutable polling schema into default Debezium SMT:** state updates are not equivalent to event inserts.
20. **Measuring only outbox inserts, not oldest pending age:** backlog can grow unnoticed indefinitely.
21. **Not versioning event schemas:** older consumers fail to parse newer messages.
22. **Serializing JPA entities/secrets/PII into payloads:** creates long-lived copies of sensitive data.
23. **No shutdown/restart tests:** pending/leased jobs get stuck after deploys.
24. **No runbook for extended broker downtime:** outbox DB table grows until disk is full.
25. **Using an H2 in-memory demo as proof of crash durability:** in-memory H2 loses data on process restart.

## 17. Test plan from unit tests to failure injection

| Test case | Expected behavior |
| --- | --- |
| Successful use case | 1 Order + 1 outbox row in the same commit |
| Business exception after both INSERTs | Neither Order nor outbox exists from the rolled-back transaction |
| Outbox insert fails | Order transaction also rolls back |
| Relay picks up pending | Sends with stable `eventId`, marks `SENT` after ack |
| Transient broker publish failure | Row stays retryable with backoff |
| Broker acks but relay crashes before `SENT` | Redelivered after restart, consumer deduplicates |
| Consumer DB fails after inbox insert | Both inbox and DB side effect roll back |
| Message redelivered | Unique key prevents repeating DB effect |
| Multiple relay workers | Claim/lease prevents stuck jobs or corrupted state |
| Lease timeout/race | Stale token does not overwrite newer claim |
| Multiple versions for same aggregate | Ordering/version guard protects state |
| Relay shut down mid-batch | Pending/leased rows remain recoverable |
| Outbox retention cleanup | Deletes only delivered rows eligible for deletion |
| CDC connector restarts | Offset/replay, key/type mapping, and dedup behave correctly |
| New schema version | Consumer backward/forward compatibility per contract |
| Prolonged broker downtime | Backlog alerts fire without silently exhausting disk |
| Payload contains sensitive data | No leaks via outbox/logs/broker |
| Multi-tenant | Correct per-tenant routing and authorization |

### 17.1. Unit tests differ from integration tests

A unit test can mock `OutboxRepository` to verify the service calls insert after creating an Order; it **does not prove transaction atomicity**. Integration tests with a real database and Spring transaction manager are what verify rollback of both rows when an exception is thrown.

### 17.2. Testing the broker ack gap

To verify duplicate handling, inject a failure point **after publish ack and before marking `SENT`**. Do not only simulate “broker did not receive” because that exercises a different failure path. The section 11 demo simulates this exact ack gap to show `CONSUMER_DUPLICATE` when the relay retries.

### 17.3. Testing real process restarts

With real PostgreSQL/MySQL or an equivalent durable DB:

1. Commit business + outbox rows.
2. Stop/kill the relay before sending, or after broker acceptance before marking `SENT`.
3. Restart the relay.
4. Verify the row is claimed/retried.
5. Verify the consumer is idempotent in its own database.
6. Check offsets/checkpoints and cleanup so no messages are lost or endlessly looped.

An in-memory H2 test **cannot substitute** for this restart test.

## 18. Production deployment checklist

- [ ] Business state and outbox use the same local database transaction?
- [ ] Outbox written directly in the use-case transaction, not waiting for async after-commit?
- [ ] Event ID/aggregate ID/version/schema version clearly defined?
- [ ] Relay is clearly polling or CDC, without mixing state protocols?
- [ ] `SENT` marked only after broker ack per contract?
- [ ] When the broker is down, rows retain a retry path and backoff?
- [ ] Multi-worker polling has valid claim/lease/fencing?
- [ ] Batch sizes, queue capacities, and network concurrency are bounded?
- [ ] Retry budgets, poison-message quarantine, and runbooks in place?
- [ ] Consumer deduplicates by stable `eventId` within a local transaction?
- [ ] External API side effects have dedicated idempotency/reconciliation?
- [ ] Aggregate ordering/version guards in place where required?
- [ ] Metrics exist for oldest pending age, sent/failed/retry/duplicate?
- [ ] Disk/table growth monitoring and cleanup/retention configured?
- [ ] Outbox/broker/log payloads classified, encrypted, and access-controlled?
- [ ] Integration tests cover commit/rollback and crash/ack-gap?
- [ ] Relay shutdown/restart, broker failures, and CDC offsets rehearsed?
- [ ] API SLAs clearly state accepted/committed vs. external processing completed?

## 19. Self-check exercises

1. Why does `@Transactional` around `orders.save()` and `broker.publish()` not create an atomic write to both the DB and the broker?
2. If the outbox and Order are written to two independent databases, are they still in the same local transaction?
3. The relay received a broker ack but crashed before marking `SENT`. What can happen after restart?
4. Why must the consumer keep `eventId` stable and use a unique constraint/inbox?
5. The inbox insert committed, yet updating the DB side effect failed: what is wrong with this design?
6. Can `@TransactionalEventListener(AFTER_COMMIT)` replace an outbox to guarantee delivery across crashes?
7. In the demo, why is `ORDERS=1` even though `place(...)` was called twice?
8. Why does the demo print `BROKER_ACCEPTED evt-101` twice while `NOTIFICATION_EFFECTS=1`?
9. How do a polling relay and a Debezium CDC outbox differ regarding `PENDING`/`SENT`/`INSERT`?
10. Why must the `SENT` update check the claim token/affected row count in a multi-worker environment?
11. What does `FOR UPDATE SKIP LOCKED` help with, and why shouldn’t the lock be held while calling the broker?
12. What problem does `aggregateVersion` solve when two events for the same aggregate are processed out of order?
13. Does a broker ack mean the consumer has finished writing to its DB?
14. If the broker is down for three days, what should be monitored?
15. If an event contains an email/password, does an outbox increase or decrease data exposure risk?
16. When do you choose polling vs. CDC?

**Guidance:** (1) a local DB transaction does not span the broker; (2) no; (3) the same event is resent, possibly duplicating; (4) deduplication; (5) the consumer may skip even though the effect did not succeed; (6) no; (7) the second call threw and rolled back; (8) unique inbox prevented duplicate DB effects; (9) polling typically updates state, while the default CDC router processes inserts via logs/offsets; (10) prevents stale updates; (11) partitions claims across workers and reduces DB lock duration; (12) ordering/skipping stale events; (13) no; (14) pending age, disk, retries, error/consumer lag; (15) increases storage locations if data is not minimized; (16) depends on infrastructure, latency, load, and operations.

## 20. Summary

The **transactional outbox** resolves the inconsistency window between the business database and the intent to emit external messages by writing **both in a single local transaction**. The **relay process** decouples network event delivery after commit, using polling or CDC, and takes responsibility for retries, acknowledgments, recovery, and observability.

Key points to remember:

- Order/business state and outbox intent **commit/roll back together**.
- The relay reads committed rows, sends to the broker, and marks `SENT` only after proper ack.
- A relay crash after broker acceptance before updating status can cause **duplicates**.
- Consumers need a stable `eventId`, inbox/idempotency, and a transaction for DB side effects.
- Polling relays and CDC/Debezium do not share all schema/status assumptions.
- Ordering, leases/fencing, retries, dead-lettering, retention, and monitoring are part of production design.
- `@EventListener`, `@Async`, or `@TransactionalEventListener(AFTER_COMMIT)` **do not replace a durable outbox on their own**.
- All durable payloads require schema versioning, data minimization, and security controls.

An outbox **does not turn a distributed system into a single transaction**. It establishes a recoverable event delivery path so services can handle eventual consistency in a controlled way.

## References

- Spring Framework — *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — *Programmatic Transaction Management and DataSourceTransactionManager*: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — *JDBC Core / JdbcTemplate*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Debezium — *Outbox Event Router*: https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- Microservices Patterns — *Transactional Outbox*: https://microservices.io/patterns/data/transactional-outbox.html
