# Transactions, Outboxes, and the Relationship Between Database Writes and Sending Messages

In the **Messaging** group of the **Spring Boot - testing** module, a common requirement is: *when an order is created successfully in the database, the system must send an OrderCreated event to RabbitMQ or Kafka*. It seems as simple as putting both calls inside `@Transactional`:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.save(order);
    rabbitTemplate.convertAndSend(
            "orders.exchange", "orders.created", order);
}
```

However, **this is not an atomic transaction across the database and the broker**. `@Transactional` with `DataSourceTransactionManager` primarily manages JDBC resources. Brokers have their own connections, channels, transactions, and acks. If publishing succeeds and the database rolls back, consumers may see an order that never committed; if the database commits and publishing fails, the order exists without an event. Either failure creates the **dual-write problem**.

This lesson explains commit boundaries, failure windows, transactional outboxes, relays/pollers, publisher confirms, retries, idempotent inboxes, and how to test from unit tests up to broker integration. The hands-on example uses **Java 17+, Spring Boot 3.5, Spring JDBC, H2, RabbitMQ, Testcontainers, and JUnit Jupiter**. The core idea is not maximizing mocks, but testing **the right reliability contract**:

- Same database transaction: inserting the business row **and** outbox row must **commit together or roll back together**.
- Post-commit: a relay reads committed outbox rows, publishes to the broker, confirms where required, and marks published.
- When the broker is temporarily unavailable: the event stays in the outbox for retry rather than vanishing just because the HTTP request returned success.
- When publishing succeeds yet marking published fails: the event may be **sent again**; consumers need **idempotency** keyed on `eventId`.
- When testing: distinguish the database having an outbox row, the producer being called, the broker confirming publish, the queue receiving the message, and the consumer committing its side effect. Those are **five distinct levels of evidence**.

The lesson includes compilable Java sources for a configured Spring Boot project, a SQL schema, unit tests, Spring JDBC transaction tests, RabbitMQ Testcontainers integration, a Java SE demo with exact stdout, error/QA checklists, and connections to Kafka/Debezium CDC.

## 1. Three resources do not automatically share one transaction

Consider an order-creation application:

```text
HTTP request
    |
    v
OrderService @Transactional
    |
    +---- JDBC INSERT orders -------[Database transaction]
    |
    +---- RabbitTemplate.send ------[AMQP connection/channel]
    |
    v
HTTP response
```

A Spring JDBC transaction is typically a `DataSourceTransactionManager` or `JdbcTransactionManager` managing **a database connection bound to the current thread**. RabbitMQ or Kafka uses a **broker protocol**; a message does not "join the same JDBC transaction" simply because it was sent inside a `@Transactional` method.

**Distinguish:**

| Operation | Who controls it? | When do you have proof? |
| --- | --- | --- |
| `INSERT orders` | JDBC transaction manager | Database COMMIT succeeds |
| `INSERT outbox_events` | **Same** JDBC transaction manager | Committed together with the order in DB |
| AMQP publish | `RabbitTemplate`/AMQP channel | Broker publisher confirm or error |
| Broker routes to queue | Exchange/binding/queue | Publisher returns/queue observation per config |
| Consumer processing | Listener container + application | Separate DB side-effect/ack/offset observation |

**Publisher confirm ACK is not consumer ACK.** RabbitMQ confirms it processed the publish at the broker per publisher-confirm semantics; the message may still sit unread by any consumer, unprocessed by the handler, and uncommitted in the consumer's DB. Publisher returns additionally detect **unroutable** messages when mandatory and returns are enabled.

With Kafka, broker producer transactions and Spring Kafka transaction synchronization can coordinate with JDBC, yet **still do not automatically form a distributed atomic commit with JDBC**. Always analyze commit order and failure windows.

## 2. Dual writes: every ordering has an inconsistency window

Two common direct orderings:

### Approach A: send message first, commit database second

```text
BEGIN DB TX
INSERT order
PUBLISH OrderCreated  --> broker accepts
ROLLBACK DB TX (or server crash)
----------------------------------
Consumer receives event, order does not exist.
```

If subscribers update inventory, send emails, or charge payments on that event, consequences happen even though the order was never durably stored.

### Approach B: commit database first, send message second

```text
BEGIN DB TX
INSERT order
COMMIT DB TX
PROCESS CRASH / network failure
PUBLISH OrderCreated never happens
----------------------------------
Order exists, event is lost.
```

Approach B avoids "phantom events" yet still causes **missing events**. Client HTTP retries might even create duplicate orders if there is no idempotency key.

### Why doesn't "putting it inside `@Transactional`" fix it?

```java
@Transactional
public void placeOrder() {
    jdbc.update("INSERT INTO orders ...");
    rabbitTemplate.convertAndSend(...);
}
```

JDBC commit occurs when the Spring transactional interceptor exits the method. `RabbitTemplate` has its own publish path. If sending succeeds, the DB commit can still fail; if the broker accepts the publish yet the ack back to the producer is lost, the producer does not know the outcome. Returning or throwing from the method does not prove both resources agree.

### What about `@TransactionalEventListener(AFTER_COMMIT)`?

This helps when an event should only be emitted **after the DB commits**:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    rabbitTemplate.convertAndSend(...);
}
```

This is an illustrative snippet requiring imports and Spring listener configuration. It **avoids publishing before commit**, yet the callback runs **in-process**. Crashing right after COMMIT and before the callback, broker unavailability, or callback failure can still lose the event. `@Async` merely moves sending to another thread without making the callback durable.

**When events must survive crashes**, store a **durable record in the same database transaction** — a transactional outbox — or use an architecture with equivalent verified transactional guarantees.

## 3. Transactional outbox: turning two writes into one DB transaction

The **transactional outbox pattern** splits two steps:

1. **Request transaction:** INSERT the business row and INSERT the outbox row **in the same DB transaction**. On failure, both roll back.
2. **Out-of-band relay:** reads committed outbox rows, publishes to the broker, confirms under policy conditions, and marks published. When publish outcome is uncertain, keep the row for retry.

```text
Request thread                     Relay worker
--------------                     ------------
BEGIN DB TX
 INSERT orders
 INSERT outbox_events (PENDING)
COMMIT DB TX
   |
   v
Business row + event both durable
                                  |
                         SELECT pending outbox
                                  |
                         PUBLISH to RabbitMQ
                                  |
                         Wait publisher confirm
                                  |
                         UPDATE state=PUBLISHED
                                  |
                              Consumer
                                  |
                      Deduplicate by eventId
                      Apply side effect + inbox TX
```

**Core guarantee:** there is no state where "the order committed without recording the intent to emit the event", provided both inserts genuinely share **the same datasource, the same JDBC transaction, and the same commit**. This does not mean the broker receives the event instantaneously after COMMIT; the relay may lag or encounter temporary errors.

### Why not DELETE outbox rows immediately upon publish?

You can delete or mark rows after publishing depending on design. The example uses `state=PENDING/PUBLISHED` for easy observation and testing. Production needs retention/cleanup so the table does not grow unboundedly. When using **CDC + Debezium Outbox Event Router**, the convention is normally **INSERT-only events**, and updating state on the same outbox table may not fit the default SMT. **Do not copy this mutable-state polling schema directly into Debezium and expect it to work**: pick your relay mechanism first and design the schema to match.

## 4. Failure windows table for an outbox

| Failure point | Business row | Outbox row | Message broker | Required behavior |
| --- | --- | --- | --- | --- |
| Before request COMMIT | Rolled back | Rolled back | Not sent | No event emitted |
| DB COMMIT succeeds, relay hasn't run | Exists | `PENDING` | Absent | Relay sends later |
| Relay hits network error before publish | Exists | `PENDING` | Absent or unknown | Retry |
| Broker accepts publish yet confirm is lost | Exists | `PENDING` | **May have received** | Retry may duplicate |
| Broker ACKed, process dies before mark | Exists | `PENDING` | Received | Retry → duplicates possible |
| Marked `PUBLISHED` successfully | Exists | `PUBLISHED` | Broker confirmed/routed per policy | Do not resend unless recovering |
| Consumer writes DB then dies before ACK | Exists | `PUBLISHED` | May redeliver | Idempotent consumer |
| Consumer handler fails | Exists | `PUBLISHED` | Retry/DLQ per config | No repeated bad effects |

This table is a **state model**, not a promise that brokers provide exactly-once. With a polling relay delivering at-least-once and consumers potentially seeing duplicates, the practical target is **at-least-once delivery + idempotent effects**.

**You cannot eliminate duplicates merely by "send then mark"**: there is always a gap between two independent actions. Marking before publishing risks **losing messages** on crash; hence the standard choice is accepting possible duplicates and deduplicating on the consumer.

## 5. Designing the event envelope and outbox row

A well-formed event should contain:

- `eventId`: **globally unique identifier per event**, used for deduplication/inbox, tracing, and correlation.
- `aggregateId`: identifier of the order/customer; with Kafka, usable as the partition key to preserve per-aggregate ordering.
- `eventType`: e.g., `order.created`.
- `schemaVersion`: payload version for producer/consumer evolution.
- `payload`: required data (avoiding unnecessary PII/secrets).
- `createdAt`: database creation timestamp; not a sufficiently strong ordering key in every case.
- `state`, `attempts`, `publishedAt`: meant for **polling relays**, not every CDC schema.

Example payload:

```json
{
  "eventId": "evt-101",
  "orderId": "ORD-101",
  "quantity": 2,
  "schemaVersion": 1
}
```

In the runnable code, `ObjectMapper` serializes a Java record to JSON. The message also carries an AMQP header `eventId` so consumers do not have to parse the body just to extract the deduplication key.

**Do not confuse:**

- One aggregate can emit multiple events → each event needs its own `eventId`.
- Retried HTTP requests with the same idempotency key must not create multiple orders/events unintentionally.
- `created_at` timestamps can collide or differ from commit order; if strict per-aggregate ordering is required, design `aggregateVersion`/sequences and matching serialization/partition keys.
- An event published multiple times still keeps the **same `eventId`**, because it is a retry of the same logical event.
- A request writing multiple business rows/events must keep them in the same transaction when they belong to one atomic business operation.

## 6. Testing plan before writing Java

| Test level | Purpose | Broker? | Key assertions |
| --- | --- | --- | --- |
| Java unit | Validate input, build event/payload | No | Accurate mapping, IDs, and boundaries |
| JDBC transaction integration | `orders` + `outbox_events` atomicity | No | Success: both present; failure: both roll back |
| Relay unit | Retry/failure/mark behavior | Mock publisher | Publish fails → stays `PENDING`; succeeds → marks |
| Rabbit broker integration | `RabbitTemplate` → exchange → queue | **Real RabbitMQ** | Confirms, routing, body, `eventId` header |
| Consumer idempotency integration | Duplicate same `eventId` | Real DB + broker/handler | Business effect runs once only |
| E2E | Request → DB → outbox → broker → consumer DB | Real DB/broker | End-to-end contract and cleanup |

**A green test calling only `Mockito.verify(rabbitTemplate).convertAndSend(...)` does not prove the message reached the broker.** Conversely, a test reading a message from a RabbitMQ queue does not prove the consumer committed its business side effects.

This lesson provides full implementations across **DB atomicity, relay unit, and broker integration**. The inbox/idempotent consumer section is presented as a separate pattern with SQL and engine notes; do not claim it is exercised by the publisher test suite.

## 7. Spring Boot 3.5 / Java 17 project

The sample project uses Spring JDBC and RabbitMQ; H2 is on the test classpath only.

```text
src/
├── main/
│   ├── java/example/outbox/
│   │   ├── OutboxApplication.java
│   │   ├── OrderCreatedEvent.java
│   │   ├── OutboxEvent.java
│   │   ├── OrderStore.java
│   │   ├── OutboxStore.java
│   │   ├── OrderCommandService.java
│   │   ├── EventPublisher.java
│   │   ├── OutboxTopology.java
│   │   ├── RabbitOutboxPublisher.java
│   │   ├── OutboxRelay.java
│   │   ├── OutboxPollingJob.java
│   │   └── OutboxCrashModel.java
│   └── resources/application.properties
└── test/
    ├── resources/schema.sql
    └── java/example/outbox/
        ├── AtomicOutboxTest.java
        ├── OutboxRelayUnitTest.java
        ├── RabbitOutboxIntegrationTest.java
        └── OutboxCrashModelTest.java
```

There is no HTTP controller in the example so we can focus on **transaction + outbox + broker**. A web/controller layer can invoke `OrderCommandService.create(...)` and return 201 after the DB commit, without blocking for the consumer inside the same HTTP request unless the contract demands it.

### 7.1. Gradle dependencies

Inside a Gradle project already configured with the Spring Boot plugin, Java 17+ toolchain, repositories, and **Spring Boot 3.5.x** dependency management/BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **dependencies and test-task snippet**, not a standalone build file. Spring AMQP/Jackson/Testcontainers versions are governed by the Boot 3.5 BOM. Testcontainers **2.x** may change the RabbitMQ module's group/artifact/package; this example targets **Testcontainers 1.x** for consistent imports.

When running the app outside tests, configure a real database, migrations, RabbitMQ host/credentials, and polling schedule. `com.h2database:h2` in `testRuntimeOnly` **does not** provide a production datasource. Never put production secrets in test fixtures.

### 7.2. `OutboxApplication.java`

Create `src/main/java/example/outbox/OutboxApplication.java`:

```java
package example.outbox;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class OutboxApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboxApplication.class, args);
    }
}
```

`@EnableScheduling` enables the polling job when turned on via property. In this lesson's tests, the polling job is **off by default** so assertions do not race against the scheduler.

### 7.3. `application.properties`

Create `src/main/resources/application.properties`:

```properties
# Correlated publisher confirms + detect unroutable messages.
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true

# Explicitly enable the polling job only where desired.
app.outbox.polling.enabled=false
```

The first three properties are required for `RabbitOutboxPublisher` to use `CorrelationData.getFuture()` and `getReturn()` meaningfully.

- **Publisher confirm:** broker returns ACK/NACK for the publish.
- **Publisher return + mandatory:** broker notifies when a message fails to route to any queue per rules. A broker ACK **can still be true for an unroutable message**, so never check only `confirm.isAck()`.
- **Polling disabled by default:** tests/manual demos call `relay.flushOnce()` explicitly. In production, set `app.outbox.polling.enabled=true` only after configuring the database, broker, monitoring, claim/locking, and appropriate retries.

**Do not equate broker confirm with consumer completion.** It is merely a sufficient step to mark `PUBLISHED` in the relay, depending on the system's delivery policy.

## 8. SQL schema: business and outbox in the same database

Create `src/test/resources/schema.sql` (H2 2.x):

```sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
        CHECK (quantity BETWEEN 1 AND 100)
);

CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload VARCHAR(2000) NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING', 'PUBLISHED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    CONSTRAINT fk_outbox_order FOREIGN KEY (aggregate_id)
        REFERENCES orders(order_id)
);

CREATE INDEX idx_outbox_pending
    ON outbox_events(state, created_at);
```

**Properties to note:**

- `orders.order_id` is the example's business primary key.
- `outbox_events.event_id` is the unique event key. Never generate a new ID on retries of **the same event**.
- The FK enforces that the outbox references a real order; within one transaction, inserting the order first and then the outbox row is valid.
- `state=PENDING/PUBLISHED` tracks the **polling relay's** state, not whether consumers have processed the event.
- `attempts` increments when the relay hits errors/uncertainty; needs metrics/alerts and realistic retry caps.
- `published_at` aids operational tracking, not proof every consumer received the event.
- H2 `VARCHAR`/timestamps/indexes may behave differently from production PostgreSQL; production-database integration tests need real migrations and matching dialects.
- The schema has no lease/owner/claim columns. **The sample relay is only safe for a single worker**, not multi-instance processing. Production hardening covers that later.

With a real database, manage schemas using Flyway/Liquibase; this simple test schema demonstrates transaction atomicity. Never run both `schema.sql` and migrations creating the same tables simultaneously.

## 9. Domain event: `OrderCreatedEvent.java`

Create `src/main/java/example/outbox/OrderCreatedEvent.java`:

```java
package example.outbox;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        int quantity,
        int schemaVersion) {
}
```

This record is the payload serialized to JSON in `OrderCommandService`. It **does not** carry RabbitMQ delivery tags, correlation data, or transaction state. `eventId` supports deduplication, `orderId` identifies the aggregate, and `schemaVersion` supports compatibility.

Create `src/main/java/example/outbox/OutboxEvent.java`:

```java
package example.outbox;

public record OutboxEvent(
        String eventId,
        String aggregateId,
        String eventType,
        String payload,
        int attempts) {
}
```

This is the row model for the relay, not a JPA entity. It holds only the fields needed to publish; `state=PENDING` is filtered in the `SELECT` query rather than carried in the record.

## 10. `OrderStore`: works strictly with JDBC

Create `src/main/java/example/outbox/OrderStore.java`:

```java
package example.outbox;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {
    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String orderId, int quantity) {
        jdbc.update("""
                INSERT INTO orders(order_id, quantity)
                VALUES (?, ?)
                """, orderId, quantity);
    }

    public int countById(String orderId) {
        Integer result = jdbc.queryForObject("""
                SELECT COUNT(*) FROM orders
                WHERE order_id = ?
                """, Integer.class, orderId);
        return result == null ? 0 : result;
    }
}
```

The store **does not open its own transaction**. `JdbcTemplate` participates in the connection bound to the thread by Spring's transaction manager; thus the order INSERT and outbox INSERT inside the service commit/roll back together.

**Avoid using `new JdbcTemplate(customDataSource)` pointing to a different datasource in `OutboxStore`.** If each store uses a separate database/transaction manager, `@Transactional` alone no longer gives you atomicity.

## 11. `OutboxStore`: insert, pending, mark, and record failure

Create `src/main/java/example/outbox/OutboxStore.java`:

```java
package example.outbox;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxStore {
    private final JdbcTemplate jdbc;

    public OutboxStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(OutboxEvent event) {
        jdbc.update("""
                INSERT INTO outbox_events
                    (event_id, aggregate_id,
                     event_type, payload)
                VALUES (?, ?, ?, ?)
                """,
                event.eventId(),
                event.aggregateId(),
                event.eventType(),
                event.payload());
    }

    public List<OutboxEvent> findPending(int limit) {
        return jdbc.query("""
                SELECT event_id, aggregate_id,
                       event_type, payload, attempts
                FROM outbox_events
                WHERE state = 'PENDING'
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (rs, rowNumber) -> new OutboxEvent(
                        rs.getString("event_id"),
                        rs.getString("aggregate_id"),
                        rs.getString("event_type"),
                        rs.getString("payload"),
                        rs.getInt("attempts")),
                limit);
    }

    public void markPublished(String eventId) {
        int updated = jdbc.update("""
                UPDATE outbox_events
                SET state = 'PUBLISHED',
                    published_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                  AND state = 'PENDING'
                """, eventId);

        if (updated != 1) {
            throw new IllegalStateException(
                    "outbox state transition failed");
        }
    }

    public void recordFailure(String eventId) {
        jdbc.update("""
                UPDATE outbox_events
                SET attempts = attempts + 1
                WHERE event_id = ?
                  AND state = 'PENDING'
                """, eventId);
    }

    public String stateOf(String eventId) {
        return jdbc.queryForObject("""
                SELECT state FROM outbox_events
                WHERE event_id = ?
                """, String.class, eventId);
    }

    public int countByEventId(String eventId) {
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM outbox_events
                WHERE event_id = ?
                """, Integer.class, eventId);
        return count == null ? 0 : count;
    }
}
```

**Semantic notes:**

- `insert(...)` joins the transaction opened by the service; SQL adds the event only when the business operation succeeds.
- `findPending(limit)` is a **simple polling query without row claiming/locking**. Two relay instances could read the same `PENDING` event and publish twice; this sample intentionally targets **a single worker**.
- `markPublished(...)` runs **only after the publisher reports send conditions succeeded**. If it fails, a retry may republish; consumers must tolerate that.
- `recordFailure(...)` increments attempts without implementing retry backoff, jitter, or max attempts itself. The operations section explains how to add them.
- `created_at` gives approximate ordering, not a replacement for aggregate sequences when strict per-order ordering is required.

Never wrap `findPending → network publish → markPublished` in one long JDBC transaction spanning the network call; that holds row locks/connections across I/O and still **does not** make publishing atomic with the DB.

## 12. `OrderCommandService`: atomic order + outbox insert

Create `src/main/java/example/outbox/OrderCommandService.java`:

```java
package example.outbox;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final OrderStore orders;
    private final OutboxStore outbox;
    private final ObjectMapper mapper;

    public OrderCommandService(
            OrderStore orders,
            OutboxStore outbox,
            ObjectMapper mapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.mapper = mapper;
    }

    @Transactional
    public void create(
            String orderId, int quantity, String eventId) {
        if (orderId == null || orderId.isBlank()
                || eventId == null || eventId.isBlank()
                || quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "invalid order command");
        }

        OrderCreatedEvent event =
                new OrderCreatedEvent(
                        eventId, orderId, quantity, 1);

        final String payload;
        try {
            payload = mapper.writeValueAsString(event);
        } catch (JsonProcessingException error) {
            throw new IllegalStateException(
                    "cannot serialize order event",
                    error);
        }

        orders.insert(orderId, quantity);
        outbox.insert(new OutboxEvent(
                eventId, orderId,
                "order.created", payload, 0));
    }
}
```

**This is the heart of the transactional outbox.** When invoked through the Spring-managed service proxy, `@Transactional` opens a transaction on the JDBC datasource. Both stores share **the same `JdbcTemplate`/DB connection infrastructure**:

```text
BEGIN
  INSERT orders
  INSERT outbox_events
COMMIT
```

If `outbox.insert(...)` fails due to a duplicate `event_id`, Spring JDBC throws an unchecked `DataIntegrityViolationException`/`DuplicateKeyException`; by default, Spring rolls back **the preceding order INSERT as well**. Hence a test should force an outbox failure after the order insert and verify the new order **does not exist**.

**Why serialize before INSERT?** If serialization fails, no JDBC write happens; even if writes occurred first and serialization failed later, a runtime exception rolls back properly when the transaction is active. This ordering keeps code clean, while atomicity comes from sharing **the same database transaction**.

**Why not send via `RabbitTemplate` here?** Once the request method finishes, the DB durably holds the **intent to emit the event**. The relay sends later; broker outages never cause order creation requests to roll back needlessly or leave a dual-write gap.

**Another limitation:** if a client retries a request after a timeout, `orders.order_id` and `eventId` need a stable business idempotency mechanism. For example, catching `DuplicateKeyException` to return conflict, or in production returning the previously created result for the same request idempotency key.

## 13. `EventPublisher` port, RabbitMQ topology, and publisher confirms

### 13.1. `EventPublisher.java`

Create `src/main/java/example/outbox/EventPublisher.java`:

```java
package example.outbox;

public interface EventPublisher {
    void publish(OutboxEvent event);
}
```

This port lets us **unit-test the relay without a broker**. Tests mocking `EventPublisher` can simulate success, network failures, and ambiguous publishes, though they do not prove real exchanges/routing. Broker integration tests use the Spring AMQP implementation.

### 13.2. `OutboxTopology.java`

Create `src/main/java/example/outbox/OutboxTopology.java`:

```java
package example.outbox;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OutboxTopology {
    public static final String EXCHANGE =
            "lesson.outbox.exchange";
    public static final String ROUTING_KEY =
            "lesson.order.created";
    public static final String QUEUE =
            "lesson.order.events";

    @Bean
    DirectExchange outboxExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue outboxQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding outboxBinding(
            @Qualifier("outboxQueue") Queue queue,
            @Qualifier("outboxExchange")
                    DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(ROUTING_KEY);
    }
}
```

Spring AMQP's `RabbitAdmin` declares the exchange/queue/binding beans on the broker once a connection forms, under appropriate default auto-declare settings. The integration test connects via Testcontainers and reads directly from this queue to verify routing.

**Not every app has permissions to auto-declare production topology.** When using a RabbitMQ operator/IaC, verify compatible names/arguments/bindings; do not rely on tests creating queues differently from production.

### 13.3. `RabbitOutboxPublisher.java`

Create `src/main/java/example/outbox/RabbitOutboxPublisher.java`:

```java
package example.outbox;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class RabbitOutboxPublisher
        implements EventPublisher {

    private final RabbitTemplate template;

    public RabbitOutboxPublisher(
            RabbitTemplate template) {
        this.template = template;
    }

    @Override
    public void publish(OutboxEvent event) {
        CorrelationData correlation =
                new CorrelationData(event.eventId());

        template.convertAndSend(
                OutboxTopology.EXCHANGE,
                OutboxTopology.ROUTING_KEY,
                event.payload(),
                message -> {
                    MessageProperties properties =
                            message.getMessageProperties();

                    properties.setMessageId(event.eventId());
                    properties.setHeader(
                            "eventId", event.eventId());
                    properties.setHeader(
                            "eventType", event.eventType());
                    properties.setContentType(
                            MessageProperties.CONTENT_TYPE_JSON);
                    return message;
                },
                correlation);

        try {
            CorrelationData.Confirm confirm =
                    correlation.getFuture().get(
                            5, TimeUnit.SECONDS);

            if (!confirm.isAck()
                    || correlation.getReturn() != null) {
                throw new IllegalStateException(
                        "broker did not confirm routed publish");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "publisher interrupted", error);
        } catch (ExecutionException
                 | TimeoutException error) {
            throw new IllegalStateException(
                    "publisher confirm unavailable", error);
        }
    }
}
```

**Three layers to distinguish:**

1. `RabbitTemplate.convertAndSend(...)` writes the message onto the AMQP channel; the method returning **does not** prove the broker processed the publish.
2. `CorrelationData.getFuture().get(...)` awaits the publisher confirmation. `confirm.isAck()` shows the broker ACKed the publish; `false` may carry a reason.
3. Non-null `correlation.getReturn()` means the message was **returned as unroutable** when returns/mandatory are enabled. The broker can still ACK a publish to an exchange even when no queue receives it; **check both confirm and return** when the contract requires routing.

**Setting `spring.rabbitmq.publisher-confirm-type=correlated`, `publisher-returns=true`, and `template.mandatory=true` is mandatory for the example's semantics.** If any property is off, `getFuture()` may never complete or `getReturn()` will not surface unroutable messages as expected.

**Why must timeouts be treated as uncertain state?** The producer may miss the ACK due to a network drop even though the broker received the message. The relay keeps the event `PENDING` and retries; consumers must deduplicate `eventId`. Never "fix" timeouts by marking `PUBLISHED` to avoid duplicates — that can lose events.

**Scope of guarantee:** publisher confirms/returns do not prove consumers processed or committed. RabbitMQ durability, persistent delivery mode, quorum queues, confirm-after-fsync, and broker restart tests need dedicated config and assertions when required by the contract.

## 14. `OutboxRelay`: publish first, mark second

Create `src/main/java/example/outbox/OutboxRelay.java`:

```java
package example.outbox;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OutboxRelay {
    private static final Logger log =
            LoggerFactory.getLogger(OutboxRelay.class);

    private final OutboxStore outbox;
    private final EventPublisher publisher;

    public OutboxRelay(
            OutboxStore outbox,
            EventPublisher publisher) {
        this.outbox = outbox;
        this.publisher = publisher;
    }

    public int flushOnce() {
        int published = 0;

        for (OutboxEvent event :
                outbox.findPending(50)) {
            try {
                publisher.publish(event);
                outbox.markPublished(event.eventId());
                published++;
            } catch (RuntimeException error) {
                outbox.recordFailure(event.eventId());

                log.warn(
                        "Outbox publish pending for eventId={}",
                        event.eventId());
            }
        }

        return published;
    }
}
```

**Intentionally simple code for a single relay worker:**

- No `@Transactional` spanning both network publish and DB state update.
- `findPending(50)` fetches a small batch instead of loading the entire table.
- Publisher confirms routing/publish succeeded → `markPublished`.
- Publisher errors/uncertain → stays `PENDING`, increments attempts, logs **`eventId`** without raw payloads/credentials, and retries next pass.
- A `markPublished` failure after publishing can also trigger a resend; consumers must be idempotent.
- `flushOnce()` returns the count of rows marked `PUBLISHED` in this pass, **not** how many consumers processed them.

**Do not use as-is as a production multi-instance relay.** Two instances could read the same `PENDING` row, publish twice, and one fails on mark. To scale safely, add lease/claim/ownership and matching DB locking/ack semantics; still tolerate duplicates on crashes between publish and mark.

### 14.1. Polling job enabled only intentionally

Create `src/main/java/example/outbox/OutboxPollingJob.java`:

```java
package example.outbox;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "app.outbox.polling.enabled",
        havingValue = "true")
public class OutboxPollingJob {
    private final OutboxRelay relay;

    public OutboxPollingJob(OutboxRelay relay) {
        this.relay = relay;
    }

    @Scheduled(fixedDelay = 1000)
    public void publishPending() {
        relay.flushOnce();
    }
}
```

In the test suite, `app.outbox.polling.enabled=false` so the relay runs only when tests **call it explicitly**. If the scheduler ran concurrently with tests, `PENDING`/`PUBLISHED` states could change before assertions, making tests flaky.

Production can configure poll intervals, backoff, batch size, metrics, shutdown, and graceful draining. `fixedDelay=1000` here only demonstrates the mechanism, not a recommended SLO for all workloads.

## 15. Testing order + outbox atomicity (no broker needed)

Create `src/test/java/example/outbox/AtomicOutboxTest.java`:

```java
package example.outbox;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties =
                "app.outbox.polling.enabled=false")
class AtomicOutboxTest {

    @Autowired
    private OrderCommandService command;

    @Autowired
    private OrderStore orders;

    @Autowired
    private OutboxStore outbox;

    @Autowired
    private JdbcTemplate jdbc;

    private final List<String> createdOrders =
            new ArrayList<>();

    private String orderId() {
        String value = "ORD-" + UUID.randomUUID();
        createdOrders.add(value);
        return value;
    }

    private static String eventId() {
        return "evt-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanupCommittedRows() {
        for (String id : createdOrders) {
            jdbc.update("""
                    DELETE FROM outbox_events
                    WHERE aggregate_id = ?
                    """, id);
            jdbc.update("""
                    DELETE FROM orders
                    WHERE order_id = ?
                    """, id);
        }
    }

    @Test
    void orderAndOutboxCommitTogether() {
        String order = orderId();
        String event = eventId();

        command.create(order, 2, event);

        assertEquals(1, orders.countById(order));
        assertEquals(1, outbox.countByEventId(event));
        assertEquals("PENDING", outbox.stateOf(event));

        String payload = jdbc.queryForObject("""
                SELECT payload FROM outbox_events
                WHERE event_id = ?
                """, String.class, event);

        assertTrue(payload.contains(order));
        assertTrue(payload.contains(event));
    }

    @Test
    void outboxUniqueFailureRollsBackPriorOrderInsert() {
        String first = orderId();
        String second = orderId();
        String duplicateEventId = eventId();

        command.create(first, 1, duplicateEventId);

        assertThrows(
                DataIntegrityViolationException.class,
                () -> command.create(
                        second, 3, duplicateEventId));

        assertEquals(1, orders.countById(first));
        assertEquals(0, orders.countById(second));
        assertEquals(
                1,
                outbox.countByEventId(duplicateEventId));
    }

    @Test
    void invalidQuantityDoesNotWriteEitherTable() {
        String order = orderId();
        String event = eventId();

        assertThrows(
                IllegalArgumentException.class,
                () -> command.create(order, 0, event));

        assertEquals(0, orders.countById(order));
        assertEquals(0, outbox.countByEventId(event));
    }
}
```

**Three JUnit integration methods** test database atomicity **without connecting to RabbitMQ**:

1. **Success:** after `command.create` returns and the service transaction commits, both `orders` and `outbox_events` hold rows; state remains `PENDING` because the relay has not run.
2. **Outbox failure after order INSERT:** intentionally reuses `eventId`; DB unique constraint rejects the outbox INSERT; Spring rolls back the second transaction. The second order row must not exist — this is the most critical assertion proving atomicity.
3. **Invalid input:** the service rejects before writing either table.

**Why does the test class not have `@Transactional`?** If `@Transactional` is placed on the JUnit test itself, `command.create(...)` with default `REQUIRED` joins the TestContext's uncommitted transaction while assertions run. Because this test verifies atomic rollback **after a real service commit**, it avoids test-managed transactions and cleans up in `@AfterEach` against a **test-only** database.

**Note:** these tests do not call `OutboxRelay.flushOnce()` and do not prove the broker received any message. They prove the **DB-side transaction boundary**.

## 16. Unit testing the relay with Mockito: retry and mark behavior

Create `src/test/java/example/outbox/OutboxRelayUnitTest.java`:

```java
package example.outbox;

import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class OutboxRelayUnitTest {

    private static OutboxEvent sample() {
        return new OutboxEvent(
                "evt-1", "ORD-1", "order.created",
                "{\"eventId\":\"evt-1\"}", 0);
    }

    @Test
    void successfulPublishMarksEventPublished() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);
        OutboxEvent event = sample();

        when(store.findPending(50))
                .thenReturn(List.of(event));

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(1, relay.flushOnce());

        verify(publisher).publish(event);
        verify(store).markPublished(event.eventId());
    }

    @Test
    void publisherFailureDoesNotMarkPublished() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);
        OutboxEvent event = sample();

        when(store.findPending(50))
                .thenReturn(List.of(event));
        doThrow(new IllegalStateException(
                "broker unavailable"))
                .when(publisher).publish(event);

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(0, relay.flushOnce());

        verify(store).recordFailure(event.eventId());
        verify(publisher).publish(event);
        // No markPublished calls:
        verify(store, times(0))
                .markPublished(event.eventId());
    }

    @Test
    void retryMayPublishSameEventIdAgain() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);
        OutboxEvent event = sample();

        when(store.findPending(50))
                .thenReturn(List.of(event));

        doThrow(new IllegalStateException(
                "confirm lost"))
                .doNothing()
                .when(publisher).publish(event);

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(0, relay.flushOnce());
        assertEquals(1, relay.flushOnce());

        verify(publisher, times(2)).publish(event);
        verify(store).recordFailure(event.eventId());
        verify(store).markPublished(event.eventId());
    }

    @Test
    void emptyOutboxDoesNotCallPublisher() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);

        when(store.findPending(50))
                .thenReturn(List.of());

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(0, relay.flushOnce());
        verifyNoInteractions(publisher);
    }
}
```

**Four unit methods** run without Spring context, H2, or RabbitMQ. They prove the relay calls the gateway properly, handles retries, does not mark on publisher error, and can re-publish the same `eventId` twice.

**What they do not prove:** Mockito mocks do not open AMQP connections, verify real publisher confirms, topology, or real DB updates. That is why the next section's test is needed.

**One detail:** the consecutive retry test uses a mocked `findPending(50)` always returning the same event — it **simulates** the event remaining `PENDING`. It is not a DB test proving the query filters states accurately; JDBC/integration tests cover storage.

## 17. RabbitMQ Testcontainers: real publish/confirm/routing

Create `src/test/java/example/outbox/RabbitOutboxIntegrationTest.java`:

```java
package example.outbox;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties =
                "app.outbox.polling.enabled=false")
class RabbitOutboxIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse(
                            "rabbitmq:4.1-management-alpine"));

    @Autowired
    private OrderCommandService command;

    @Autowired
    private OutboxRelay relay;

    @Autowired
    private OutboxStore outbox;

    @Autowired
    private RabbitTemplate rabbitTemplate;

    @Autowired
    private ObjectMapper mapper;

    @Autowired
    private JdbcTemplate jdbc;

    private final List<String> createdOrders =
            new ArrayList<>();

    @AfterEach
    void cleanupDatabaseRows() {
        for (String order : createdOrders) {
            jdbc.update("""
                    DELETE FROM outbox_events
                    WHERE aggregate_id = ?
                    """, order);
            jdbc.update("""
                    DELETE FROM orders
                    WHERE order_id = ?
                    """, order);
        }
    }

    @Test
    void committedOutboxEventIsPublishedToRealQueue()
            throws Exception {
        assertTrue(rabbit.isRunning());

        String order = "ORD-" + UUID.randomUUID();
        String event = "evt-" + UUID.randomUUID();
        createdOrders.add(order);

        command.create(order, 2, event);

        assertEquals("PENDING", outbox.stateOf(event));
        assertEquals(1, relay.flushOnce());
        assertEquals("PUBLISHED", outbox.stateOf(event));

        Message message = rabbitTemplate.receive(
                OutboxTopology.QUEUE, 10_000L);

        assertNotNull(message);
        assertEquals(
                event,
                message.getMessageProperties()
                        .getHeaders().get("eventId"));
        assertEquals(
                event,
                message.getMessageProperties()
                        .getMessageId());

        OrderCreatedEvent fromBroker =
                mapper.readValue(
                        message.getBody(),
                        OrderCreatedEvent.class);

        assertEquals(
                new OrderCreatedEvent(
                        event, order, 2, 1),
                fromBroker);
    }

    @Test
    void relayWithNoPendingEventsPublishesNothing() {
        assertTrue(rabbit.isRunning());
        assertEquals(0, relay.flushOnce());
    }
}
```

**Two integration methods** use a **real RabbitMQ server in Docker** and H2 for outbox/orders:

- `@Testcontainers` + static `@Container` manages RabbitMQ per class.
- `@ServiceConnection` from Spring Boot creates `RabbitConnectionDetails`; no hard-coding `localhost:5672` or credentials.
- Order/outbox rows commit before the relay runs; tests verify the transition `PENDING` → `PUBLISHED`.
- `RabbitOutboxPublisher` genuinely waits for correlated publisher confirm, checks return, and then marks `PUBLISHED`.
- `RabbitTemplate.receive(queue, 10_000L)` reads the real message from the queue (this is a **consume**, not a peek); asserts `eventId` header/`messageId` and JSON body.
- No `@RabbitListener` consumer runs in this test class; it tests **producer + broker topology/routing**, not downstream business handlers.
- The test is not annotated `@Transactional`; thus the relay reads committed outbox state rather than uncommitted test transactions.

**Critical caveat:** a publisher confirm ACK plus reading the message from the queue **does not prove** the message survives a broker restart or that downstream consumers processed it. If the contract requires durable/quorum queues, persistent delivery mode, confirm after fsync, and failover, write corresponding cluster/topology integration tests.

### Why doesn't `@ServiceConnection` replace a database transaction?

`@ServiceConnection` only provides **RabbitMQ connection details**. DB transactions are created via Spring Boot's JDBC transaction manager. It never automatically forms an XA transaction shared with RabbitMQ. The separation is verified explicitly: `OrderCommandService.create` commits the DB, the relay publishes later, and then updates state.

### Cleanup with H2 tests

Tests track each order ID individually and `@AfterEach` deletes outbox first, then orders due to the FK. The H2 test-only datasource is not production. If an assertion fails mid-test, cleanup still runs per JUnit's normal lifecycle.

**Never run these `DELETE` statements against a shared production/staging DB.** When switching to PostgreSQL Testcontainers, use an ephemeral database with matching migrations and cleanup. Under parallel tests on shared brokers/DBs, isolate queue names and data keys so tests never steal each other's messages.

## 18. Testing further when DB fails so the broker must not receive an event

An important integration test checks not only happy paths, but also failure windows:

```text
command.create(orderA, eventX) -> COMMIT
command.create(orderB, eventX) -> outbox UNIQUE error
                                     |
                                     v
                                  ROLLBACK orderB
relay.flushOnce() must see only orderA's eventX
```

`AtomicOutboxTest.outboxUniqueFailureRollsBackPriorOrderInsert()` already tests the main part: `orderB` does not remain in the DB. You can extend it with a publisher spy/fake gateway to assert the relay never publishes an event for `orderB`.

**Never test by "mocking `OutboxStore` to throw an exception and verifying the service called save"** and calling that atomicity. A mock cannot prove SQL rollback. Only transaction integration tests with a real DB (H2 or production-like engine) provide evidence for SQL commit/rollback.

Another scenario is DB commit **succeeding** while the process dies immediately after. The `PENDING` outbox row survives because it committed alongside the order. A test can insert data, shut down the service/context, and start a fresh relay pointing at the same database to prove recovery; because an H2 in-memory DB can vanish on context reset, use an appropriate DB lifecycle (e.g., a PostgreSQL container persisting across the test).

## 19. Inbox/idempotent consumer: protecting against duplicate events

A transactional outbox does not eliminate the possibility of sending an event twice. Consumers must ensure the **logical business effect applies at most once** per `eventId`.

Consumer database schema sketch:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
);
```

**Wrong approach:** `if (!exists(eventId)) { applyEffect(); insertProcessed(eventId); }` outside a transaction or without `UNIQUE`. Two consumers can both observe "not present" and both apply the side effect.

**Better approach:** the consumer performs *idempotency marking + business effect in the same DB transaction*, relying on a unique constraint to block duplicates:

```text
BEGIN consumer DB TX
  INSERT processed_events(event_id)
    -- unique constraint blocks already-processed eventId
  APPLY business projection
COMMIT consumer DB TX
ACK broker
```

If `INSERT processed_events` hits a duplicate, the consumer can detect it and ACK/no-op per policy. However, in PostgreSQL, **a constraint violation inside a transaction puts that transaction into a failed state**; do not merely catch `DuplicateKeyException` and keep issuing SQL in the same transaction as if nothing happened. Use a clean transaction boundary or an engine-appropriate idempotent insert statement.

### PostgreSQL-specific: `ON CONFLICT DO NOTHING`

Snippet **for PostgreSQL, not a standalone runnable class**:

```sql
INSERT INTO processed_events(event_id)
VALUES (:event_id)
ON CONFLICT (event_id) DO NOTHING;
```

Check affected row count:

- 1 row → new event, proceed with the business effect in **the same transaction**.
- 0 rows → duplicate, skip effect and return success per policy.
- Any other DB error → do not treat as a duplicate.

In Java/Spring JDBC you can use `NamedParameterJdbcTemplate.update(...)` with `@Transactional` on the message-handling service, ensuring both the insert and projection update share **the same datasource/transaction manager**.

### Idempotency does not automatically protect external HTTP/emails

If a consumer sent an email or charged a payment before inserting the idempotency row and then crashed, redelivery can trigger a repeat. For external APIs, pass idempotency keys to the provider when supported; use another outbox for side effects or design sagas/compensations.

Never claim system-wide exactly-once solely because of one local unique constraint. You can achieve "effectively once" for **a properly transacted and deduplicated DB side-effect scope**, not automatically for every downstream system.

## 20. Kafka, transaction synchronization, and Debezium CDC

### 20.1. Kafka producer transactions are not XA with JDBC

Spring Kafka supports Kafka transaction managers and transaction synchronization, for example:

```java
@Transactional
public void process() {
    jdbc.update("INSERT ...");
    kafkaTemplate.send("orders.events", "key", "value");
}
```

This is an **architectural snippet**, not runnable code from the RabbitMQ demo; it needs a `KafkaTemplate` bean, topic, transaction settings, and imports. When `KafkaTemplate` joins a transaction synchronized with a JDBC manager, Spring Kafka may commit the database first and then commit Kafka (or invert order via appropriate boundaries). If the second commit fails **after the first already committed**, inconsistency still occurs and must be resolved via compensation/reconciliation. <https://docs.spring.io/spring-kafka/reference/kafka/transactions.html> explains the details.

Kafka exactly-once semantics (EOS) apply **within Kafka transactions/consume-transform-produce** under specific conditions; they do not pull an external relational database into the same atomic commit. When the contract requires DB-to-Kafka reliability and crash recovery, transactional outbox/CDC is usually easier to reason about.

### 20.2. Polling relay vs. Debezium Outbox Event Router

| Aspect | Polling relay (this lesson) | CDC / Debezium |
| --- | --- | --- |
| Event detection | `SELECT` `PENDING` rows | Follows DB change log/binlog/WAL |
| Schema | Can use `state`/`attempts` | Usually `INSERT`-only outbox records |
| Operational surface | Scheduler, claim/lease, retries, status | Kafka Connect/Debezium, offsets, SMT, lag |
| Ordering | Needs sequence/claim policy | Follows commit log + connector, plus key/partition strategy |
| Failures | Retry + idempotency | CDC replay + idempotency |
| Integration | Custom publisher API | Configure matching connector/router |
| Complexity | App carries relay code | Dedicated CDC infrastructure |

Debezium Outbox Event Router reads outbox records, routes topics, and can place event IDs in message headers and aggregate IDs in record keys. **With the default Debezium SMT, do not mutate each `PENDING` row through a series of `UPDATE` states expecting the router to infer semantics**; Debezium docs note outbox rows are normally handled as insert events with dedicated handling for updates.

**Real CDC testing** requires a database transaction log, connector, Kafka broker, SMT config, offsets, and end-to-end assertions. Unit-testing a mapper or running H2 outbox tests does not prove the connector emits events as expected.

## 21. Multi-instance relay: claim/lease instead of plain `SELECT PENDING`

`OutboxStore.findPending(50)` in section 11 suits **a single worker**. With multiple replicas:

```text
Worker A: SELECT event X PENDING
Worker B: SELECT event X PENDING
Worker A: publish X
Worker B: publish X
```

Both workers can publish the same event even if only one succeeds in marking `PUBLISHED`. Idempotent consumers remain necessary, yet duplicate traffic and reordering increase.

A production polling architecture typically follows:

1. Inside a **short** DB transaction, claim a batch of pending rows: `SELECT ... FOR UPDATE SKIP LOCKED` in PostgreSQL or an engine-equivalent lock/lease mechanism.
2. Record `ownerId`, `leaseUntil`, state `IN_PROGRESS`, increment attempts, and **commit the claim**.
3. Publish to the broker **outside any DB transaction**; wait for publisher confirm/return with a timeout.
4. On success, update `PUBLISHED` guarded by `event_id` + `ownerId` + lease/version so a stale worker cannot overwrite newer state.
5. On error/timeout, retry with backoff and lease expiry; crashes before completion allow reclaiming later.
6. A reconciliation job detects stuck rows, alerts on age/attempts, and provides manual replay/recovery policies.

**Never hold row locks across network calls.** Long transactions exhaust pools/locks and stall business writes. Even with claim/lease, crashing between publish and mark still creates duplicates; consumer idempotency remains indispensable.

**Per-aggregate ordering:** if an order emits `created` and then `paid`, avoid sending `paid` before `created` across multiple workers. Consider `aggregate_version`, partition keys, claiming only the next sequence per aggregate, or serial routing per aggregate instead of relying on timestamps alone.

## 22. Testing meaningful failure injection

A solid outbox test suite goes beyond the happy path. Cover this matrix:

| Failure injection | How to simulate | What to assert |
| --- | --- | --- |
| Invalid business rule | `quantity = 0` | Neither order nor outbox exists |
| Outbox constraint failure | Duplicate `eventId` | New order rolls back |
| Broker send failure | Mock `EventPublisher` throws | Not marked published |
| Confirm timeout | Mock publisher throws timeout wrapper | Stays pending, increments attempts |
| Publish succeeds, mark fails | Stub `OutboxStore.markPublished` throws | Next pass can republish same `eventId` |
| Unroutable | Real broker, wrong routing key | Publisher return observed; not marked |
| DB outage after publish | DB fault injection / proxy | Do not assume event lost; duplicate possible |
| Consumer duplicate | Publish same `eventId` twice | Business effect at most once |
| Poison payload | Invalid schema/version | DLQ/error policy; no endless retry |
| Prolonged broker outage | Dedicated Testcontainers outage test | Outbox stays pending, retry/backoff, alert |
| Process restart | Stop/recreate relay with surviving DB | `PENDING` event published afterwards |

**What the example already covers:** transaction rollback via duplicate `eventId`; mocked publisher fail/retry/success; real RabbitMQ broker confirms and routing into the queue. The remaining rows are **extension scenarios**, not claims that all of them are already automated here.

If testing real broker outages, coordinate container lifecycles, expect connection failures with timeouts, and prevent other tests sharing a Spring context from failing due to a stopped container. Never arbitrarily call `rabbit.stop()` mid-suite while cached contexts keep stale connections.

## 23. `@Transactional` on JUnit tests can hide bugs

A test might be written as:

```java
@SpringBootTest
@Transactional
class WrongProofTest {
    @Test
    void writesOrderAndEvent() {
        command.create("ORD-1", 1, "evt-1");
        // SELECT inside the same transaction sees 2 rows.
    }
}
```

This is an **illustrative anti-pattern**, not a file in the runnable suite. Because a test-managed transaction is already active on the JUnit thread, `OrderCommandService.create` with propagation `REQUIRED` normally joins it. `SELECT`s inside the test see **uncommitted rows**; at method end, `TestContext` rolls back. It **does not prove the order and outbox survive together after a real service COMMIT**.

In `AtomicOutboxTest`, the test **omits** `@Transactional` so the service proxy commits for real. `@AfterEach` cleans up rows on the test-only datasource. Alternatively, use `TestTransaction.flagForCommit/flagForRollback/end` deliberately when inspecting post-transaction state, without confusing it with production semantics.

With RabbitMQ consumers running on separate threads, `@Transactional` on a JUnit test does not cover consumer writes either. The same holds for real HTTP calls via `@SpringBootTest(RANDOM_PORT)`. Use isolated test DBs/containers, finite timeouts, and cleanup in proper transactions.

## 24. Standalone Java SE program: duplicate after crash

To see why an **at-least-once relay** requires consumer idempotency, simulate the broker accepting an event while the relay crashes before marking. No Spring/DB/Docker required.

Create `src/main/java/example/outbox/OutboxCrashModel.java`:

```java
package example.outbox;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class OutboxCrashModel {
    private OutboxCrashModel() {
    }

    public record Result(
            int brokerDeliveries, int uniqueEffects) {
    }

    public static Result simulate() {
        String eventId = "evt-1";
        List<String> brokerDeliveries =
                new ArrayList<>();

        // Publish succeeds, yet relay crashes
        // before marking PUBLISHED:
        brokerDeliveries.add(eventId);

        // Relay restarts and resends the same eventId:
        brokerDeliveries.add(eventId);

        Set<String> processedEventIds =
                new HashSet<>();
        int applied = 0;

        for (String received : brokerDeliveries) {
            if (processedEventIds.add(received)) {
                applied++;
            }
        }

        return new Result(
                brokerDeliveries.size(), applied);
    }

    public static void main(String[] args) {
        Result result = simulate();

        System.out.println(
                "brokerDeliveries="
                        + result.brokerDeliveries());
        System.out.println(
                "uniqueEffects="
                        + result.uniqueEffects());
    }
}
```

Compile/run with JDK 17+:

```bash
javac -d out src/main/java/example/outbox/OutboxCrashModel.java
java -cp out example.outbox.OutboxCrashModel
```

**Exact** stdout:

```text
brokerDeliveries=2
uniqueEffects=1
```

Meaning:

- The broker receives the same `eventId` twice due to retry after crash.
- The consumer **simulates** deduplication with a `HashSet`, so the business effect applies only once.
- **This is only a Java SE model**, not a production transactional inbox. `HashSet` loses state on process restart, is not atomic with business DB writes, and is unsafe across multiple consumer instances. In production, use a database unique constraint/transaction or an idempotent external API.

Create `src/test/java/example/outbox/OutboxCrashModelTest.java`:

```java
package example.outbox;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OutboxCrashModelTest {
    @Test
    void duplicateDeliveryCanProduceOneLogicalEffect() {
        OutboxCrashModel.Result result =
                OutboxCrashModel.simulate();

        assertEquals(2, result.brokerDeliveries());
        assertEquals(1, result.uniqueEffects());
    }
}
```

**One JUnit unit method** verifies the model, without replacing RabbitMQ/PostgreSQL integration.

## 25. Running the tests

Unit tests without Docker:

```bash
./gradlew test --tests example.outbox.OutboxRelayUnitTest
./gradlew test --tests example.outbox.OutboxCrashModelTest
```

JDBC transaction tests using H2 and Spring context, no running broker required (does not invoke publisher):

```bash
./gradlew test --tests example.outbox.AtomicOutboxTest
```

RabbitMQ broker integration requiring Docker:

```bash
./gradlew test --tests example.outbox.RabbitOutboxIntegrationTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.outbox.OutboxRelayUnitTest"
.\gradlew.bat test --tests "example.outbox.OutboxCrashModelTest"
.\gradlew.bat test --tests "example.outbox.AtomicOutboxTest"
.\gradlew.bat test --tests "example.outbox.RabbitOutboxIntegrationTest"
```

**Expected if JDK 17+, Boot 3.5 BOM, H2 schema, and Docker image align:**

| Test class | JUnit methods | Requirements |
| --- | ---: | --- |
| `OutboxRelayUnitTest` | 4 | Mockito, no broker |
| `OutboxCrashModelTest` | 1 | Java/JUnit, no broker |
| `AtomicOutboxTest` | 3 | Spring JDBC + H2 |
| `RabbitOutboxIntegrationTest` | 2 | Spring JDBC + H2 + RabbitMQ Testcontainers |
| **Total** | **10** | Covers unit, DB, and broker tests |

These are **expected results when learners actually run the suite**; the lesson does not claim to have started Docker in the reader's environment. Gradle/JUnit logs depend on runner/version, so there is no fixed generic stdout. Only `OutboxCrashModel` as a Java SE demo has fixed stdout shown in section 24.

**A note on test context caching:** JUnit's static `@Container` stops RabbitMQ after the test class; Spring may cache `ApplicationContext` longer. When multiple classes share a cached context, align container lifecycles or declare the container as a Spring-managed bean to prevent datasources/`RabbitConnectionFactory` from pointing at a stopped container.

## 26. Observing and operating an outbox in production

An outbox without monitoring merely moves failures silently from requests to background workers. Track:

- Count of `PENDING` events; age of the oldest `PENDING` row.
- Average attempts and rows exceeding retry thresholds.
- Latency from DB COMMIT → broker confirm.
- Publisher confirm ACK/NACK counts, unroutable returns, broker connection timeouts.
- Publish rate, throughput, queue depth, consumer lag, DLQ rates.
- Masked dead-letter reasons, never logging raw sensitive payloads.
- Count of duplicate `eventId`s skipped by the inbox, count of schema-error events.
- Expired worker claims/leases, stuck jobs, reconciliation counts.
- Retention/partitioning/index size of the outbox table, `VACUUM`/cleanup on PostgreSQL.
- Alerts based on **event age** and business SLAs, not merely whether the worker process died.

**Retry/backoff:** never poll hundreds of times per second while the broker is down. Use exponential backoff/jitter, cooldowns, max attempts, and parking queues per policy; investigate poison events instead of retrying infinitely.

**Security:** event payloads may carry PII or financial data. Include only strictly necessary fields; encrypt transport, manage credentials, restrict broker/topic ACLs, and govern TTL/retention and logs. Never leak database URLs, AMQP passwords, or raw sensitive payloads in public exceptions.

**Migrations:** when evolving event schemas, bump `schemaVersion` and support old-consumer/new-producer combinations per contract. During rollouts, `PENDING` outbox rows from the previous version may still exist; relays and consumers must still read them after deployment.

## 27. Common mistakes

**1. Putting `RabbitTemplate.send` inside JDBC `@Transactional` and assuming atomicity.** Broker and DB do not automatically share a commit.

**2. Sending the event before committing the DB.** Consumers can observe a phantom order if the DB rolls back.

**3. Committing the DB first and sending the event without durable intent.** A crash in between loses the message.

**4. Treating `@TransactionalEventListener(AFTER_COMMIT)` alone as a durability guarantee.** In-process callbacks can be lost after a crash; an outbox is needed.

**5. Writing orders and outbox rows to two different databases/transaction managers.** Atomicity within one DB transaction is lost.

**6. Catching and ignoring outbox INSERT exceptions.** The business order can commit without an event; roll back or enforce an explicit strategy.

**7. Passing mocked unit tests and concluding database transactions work.** Mocks cannot prove SQL rollback.

**8. Putting `@Transactional` on JUnit tests and reading uncommitted rows.** Does not verify service commits; design assertions outside test-managed transactions.

**9. Calling `RabbitTemplate.convertAndSend` and immediately marking `PUBLISHED`.** Without awaiting publisher confirms/returns, failed sends lose events.

**10. Treating RabbitMQ confirm ACK as consumer processed/DB commit.** It is not; consumers have separate acknowledgments and transactions.

**11. Omitting `mandatory` + publisher returns and treating confirm ACK as routed.** The broker can ACK an unroutable message.

**12. Marking success on confirm timeout to fear-avoid duplicates.** Causes missing events; keep `PENDING` and tolerate retries.

**13. Marking `PUBLISHED` before publishing.** A crash after marking can permanently lose the event.

**14. Generating a new `eventId` on each retry.** Breaks deduplication; retries must preserve the **exact same `eventId`**.

**15. No consumer idempotency.** Crashes between broker publish and DB mark, or between consumer commit and ACK, can double-apply effects.

**16. Checking existence then applying effects without a unique constraint.** Two concurrent consumers can both process the event.

**17. Catching a PostgreSQL unique violation and continuing SQL in the aborted transaction.** Handle conflicts outside the transaction boundary or via `ON CONFLICT`.

**18. Two relay instances running `SELECT PENDING` without claim/lease.** Both can publish duplicates and reorder aggregate events.

**19. Holding DB transactions/row locks across network calls.** Increases contention and pool exhaustion without providing distributed atomic commits.

**20. Relying on timestamps for absolute ordering.** Timestamps can collide; use aggregate sequences/partition policies when ordering is part of the contract.

**21. Using a mutable-state polling outbox schema with default Debezium Event Router.** CDC SMTs normally process outboxes as `INSERT`-only events with distinct update semantics.

**22. Assuming Kafka EOS pulls JDBC into an XA transaction.** Analyze commit order and failure gaps rather than extrapolating from Kafka producer transactions.

**23. Relying on H2 tests to guarantee PostgreSQL deadlocks/locks/SQL dialects.** Use Testcontainers with production-like databases when risks are engine-specific.

**24. Using `@DirtiesContext` to clean committed data or broker messages.** Context reloads do not clear external DBs or queues.

**25. Missing backoff/monitoring/retention.** Outboxes silently pile up `PENDING` rows or grow unboundedly.

## 28. QA checklist and conclusion criteria

**Transaction scope:**

- Do orders and outbox share the **same datasource/transaction manager**?
- Is the `@Transactional` service invoked through its Spring proxy, with no self-invocation?
- Is there a real DB test verifying outbox INSERT failure → order rollback?
- Do tests observe state **after commit** rather than inside a test-managed transaction?
- Is broker sending kept outside request DB transactions?

**Publisher/relay:**

- Is `eventId` stable across retries and distinct from `aggregateId`?
- Are publisher confirms and returns tested per contract, not just mock method calls?
- Is broker ACK distinguished from routing, consumer processing, and DB commits?
- Do publish failures/timeouts leave the event `PENDING`?
- If publish succeeds and marking fails so it resends, do consumers tolerate duplicates?
- Is there claim/lease/ownership when running multiple relay instances?
- Is there a per-aggregate ordering policy when events depend on order?
- Are retry/backoff, alerts, and DLQ/parking policies configured?

**Consumer/idempotency:**

- Is there a processed-event unique key or idempotent external API?
- Are the deduplication marker and business DB effect atomic in the same transaction?
- Are duplicate/concurrent deliveries tested?
- Can retries after crashes safely reapply or skip?
- Are consumer ACKs/offset commits treated as a separate boundary?
- Are poison messages and old `schemaVersion`s governed by clear policies?

**Test isolation/CI:**

- Do relay unit tests run without RabbitMQ/Docker?
- Do DB atomicity tests use real H2/PostgreSQL rather than mocked JDBC?
- Does broker integration publish and receive from a real queue with finite timeouts?
- Are tests free of `@Transactional` falsely implying real commits?
- Is cleanup of orders/outbox/queues isolated without touching production data?
- Are Docker images/versions, Spring Boot/Testcontainers BOMs, and mapped ports accurate?
- Is the full suite free of context cache/container lifecycle races?
- Are production-specific SQL/CDC features covered by dedicated integration tests when needed?

**Conclusion:** a transactional outbox does not merge JDBC and the broker into one shared transaction. It replaces **two actions that are hard to commit atomically** with **one DB commit for the business row + outbox event**, delegating delivery to a recoverable relay. Because publishing and marking remain two steps, an event may still be sent more than once: **at-least-once + idempotent consumers** is the safe, testable model. Tests must verify atomicity in the DB, retry/marking in the relay, confirms/routing on a real broker, and side effects/idempotency in consumers — each level provides distinct evidence.

## 29. References

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxies, propagation, rollback, and transaction boundaries.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): differences between test transactions and application transactions.
- [Spring AMQP — RabbitTemplate and Publisher Confirms/Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData.getFuture()`, returns, mandatory, and publisher acknowledgements.
- [Spring Boot 3.5 — AMQP Messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/amqp.html): `RabbitTemplate`, `RabbitAdmin`, listener infrastructure, and configuration.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` for `RabbitMQContainer`.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): JDBC/Kafka transaction synchronization, commit order, and limitations.
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): CDC/SMT, event IDs, aggregate keys, and insert-only outbox semantics.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): RabbitMQ container; check 1.x/2.x artifacts against the project BOM.
