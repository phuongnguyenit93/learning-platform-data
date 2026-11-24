# Designing an Outbox for Integration Events in Spring Framework Application Events

## 1. Design Goal: One Business Change, One Durable Integration Event

Suppose the **Order** service writes an order to the database and needs to notify **Inventory**, **Billing**, or **Delivery**. In Spring, you can call `ApplicationEventPublisher.publishEvent(new OrderPlaced(...))` and handle the event with `@EventListener`. That works well for decoupling modules inside the same application, yet **plain Spring Application Events are not a durable cross-service messaging mechanism**.

For **integration events**, requirements are typically stronger:

- Never emit an event for an order-creation transaction that **rolled back**.
- Once the transaction commits, persist a **durable event record** for delivery even if the JVM crashes or the broker is temporarily down.
- If the relay does not know whether the previous send succeeded, it can **re-send the same `eventId`**.
- Consumers **never apply side effects twice** when an event is delivered repeatedly.
- Events have a stable format, schema, and version so services can deploy independently.
- Monitoring tracks backlogs, retries, data errors, and delivery latency.

**Transactional outbox** is a pattern meeting the first requirements: the producer writes **business data** and the **outbox record** in **the same local database transaction T1**, and a relay sends the outbox record to the broker/API after commit.

> Core guarantee: if T1 commits, both the business row and the event row exist; if T1 rolls back, both roll back. Sending the event to a broker still generally has **at-least-once** semantics, not end-to-end exactly-once. Consumers must be idempotent.

This is a **practical design** lesson: we walk from requirements, event contracts, schemas, transaction boundaries, relays, consumers, and fault injection to a production review checklist. The main example uses **Java 17, Spring Framework 6.2, Spring JDBC, and H2** so it runs easily without a real Kafka cluster.

## 2. Boundary: Domain Events vs. Integration Events

A **domain event** describes something important that just happened inside an aggregate or module, such as `OrderPlaced`. Within a Spring application, a domain event can be handled by `@EventListener` or `@TransactionalEventListener`.

An **integration event** is a **public contract between components with independent lifecycles**. Do not expose a JPA entity or internal service details directly downstream; design integration events like APIs.

| Criterion | Internal domain event | Integration event |
|---|---|---|
| Purpose | Decouple logic/modules inside one app | Synchronize events across services/systems |
| Lifespan | Often very short, inside the JVM | Can remain in DB, broker, or DLQ for days |
| Versioning | Often changes alongside one codebase | Requires schema evolution and compatibility |
| Delivery | Spring dispatch inside `ApplicationContext` | Broker/API with retries, ACKs, offsets |
| Payload | Java/domain model objects | Serialized snapshot/contract; avoid mutable entities |
| Duplicates | Depends on local flow | Must assume duplicate delivery can occur |
| Ordering | Depends on listener/dispatcher | Depends on key, partition, version, and workers |
| Security | In-process trust boundary | Cross-system trust boundary |

For example: a service may have `OrderPlacedDomainEvent(orderId, orderEntity)` internally, while the integration event is `OrderPlacedV1` containing only `eventId`, `orderId`, `tenantId`, `amountMinor`, `currency`, `aggregateVersion`, and the business timestamp. The payload does not depend on Hibernate sessions or internal database schemas.

### Do Not Turn Method Names into Contracts

`OrderCreated`, `OrderPlaced`, or `PaymentCaptured` must define **when the event is considered true**: before commit or after commit, at order placement or at payment confirmation, and whether retries/cancellations are allowed. For integration events, publish **a committed business fact** rather than a vague notification that "the service just called a create method".

## 3. Failure Matrix: Why an Outbox Is Necessary

If a service writes to a DB and also sends to Kafka/HTTP, that is a **dual-write** problem. Two operations do not automatically share one ACID transaction.

### Sending Before Commit

~~~text
BEGIN T1
  INSERT orders(id='ORD-344')
  send Kafka OrderPlaced('ORD-344') -> broker ACK
  COMMIT T1 -> fails
~~~

Consumers receive an event for an order that does not exist in the database. A broker ACK does not force the database to commit.

### Sending After Commit

~~~text
BEGIN T1
  INSERT orders(id='ORD-344')
COMMIT T1 -> succeeds
JVM crashes before calling send Kafka
~~~

The order exists, yet Inventory/Billing are never notified. If the event existed only in RAM, nothing replays it automatically when the service restarts.

### Using Only `@TransactionalEventListener(AFTER_COMMIT)`

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    kafkaTemplate.send("order-events", event.orderId(), serialize(event));
}
~~~

This is **illustrative integration code**, not standalone runnable code. `@TransactionalEventListener(AFTER_COMMIT)` ensures the callback runs only after T1 commits, yet **does not persist the event to the database before commit**. If the JVM crashes between DB commit and sending, the event is still lost. When sending asynchronously, await broker confirmation per contract; `send(...)` returning does not by itself prove the message is durable.

| Failure timing | Direct send | `AFTER_COMMIT` callback | Transactional outbox |
|---|---|---|---|
| T1 rolls back after send | Possible orphaned event | Callback does not run after rollback | Outbox also rolls back |
| Crash after T1 commit, before send | Possible lost event | Possible lost event | Outbox remains for relay |
| Broker temporarily unavailable | Requires separate retry | Requires separate retry | Relay retries from durable data |
| Send succeeds, crash before marking sent | Possible duplicate | Possible duplicate | Possible duplicate: consumer must dedupe |
| Process restart | No default event log | No default event log | Continues reading unsent outbox rows |

**An outbox does not turn the broker and database into one distributed transaction.** It shifts the critical commit point: what must be atomic is **business state + publishing intent** on one database.

## 4. Proposed Architecture Flow

~~~text
              SPRING ORDER SERVICE
                    |
             @Transactional T1
                    |
          +---------+---------+
          |                   |
          v                   v
      orders table       outbox_events table
          |                   |
          +---------+---------+
                    |
                  COMMIT
                    |
      +-------------+----------------+
      |                              |
      v                              v
  Order state                  Outbox PENDING
                                     |
                          Polling relay / CDC
                                     |
                            Kafka / RabbitMQ
                                     |
                     +---------------+--------------+
                     |                              |
                Inventory consumer             Billing consumer
                     |                              |
                durable inbox                  durable inbox
                     |                              |
                 update stock                 create invoice
                     |                              |
                 ACK message                    ACK message
~~~

There are **three transaction boundaries** that must not be conflated:

1. **Producer T1:** updates the aggregate and INSERTs the outbox row.
2. **Relay T2:** claims or marks `SENT`/retry state on the outbox. The broker send happens between steps and is not atomic with them.
3. **Consumer T3:** receives `eventId`, marks it processed, and applies DB side effects in its own transaction.

A service cannot rely on producer `@Transactional` to automatically span the consumer's DB or the broker.

## 5. Designing the Event Contract Before Writing Code

An integration event should have a stable **envelope**, with business data inside a versioned payload.

Illustrative example:

~~~json
{
  "eventId": "d51d4ab8-11b2-4e9c-9845-7a4115e5801e",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "producer": "order-service",
  "tenantId": "tenant-demo",
  "aggregateType": "Order",
  "aggregateId": "ORD-344",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T07:00:00Z",
  "correlationId": "req-demo-344",
  "data": {
    "currency": "VND",
    "amountMinor": 350000,
    "state": "PLACED"
  }
}
~~~

This is **hypothetical data**. Expressing amounts in **minor units** avoids imprecise floating-point conversions; when using VND, the system must explicitly define `amountMinor` rules per ISO currency scale. Never assume every currency has 2 decimal places.

### Responsibility of Each Field

| Field | Why is it needed? | Notes |
|---|---|---|
| `eventId` | Uniquely identifies an event occurrence; used for idempotency | Retries **preserve** `eventId` |
| `eventType` | Defines the type of fact | Do not name after frequently changing methods |
| `schemaVersion` | Controls format | Have a migration/replay strategy |
| `producer` | Ownership and operational routing | Do not use as access-control proof |
| `aggregateId` | Used as Kafka key, links to the entity | Does not replace `eventId` |
| `aggregateVersion` | Controls ordering / stale events | Must be assigned inside the aggregate's transaction |
| `tenantId` | Supports isolation/routing | Validate authorization at the consumer |
| `occurredAt` | Business timestamp | Do not assume it equals commit timestamp |
| `correlationId` | Links commands, traces, logs | Not a mandatory idempotency key |
| `data` | Immutable payload needed by consumers | Avoid unnecessary PII or entities/proxies |

Decide **event granularity**: one `OrderPlaced` for the whole aggregate or one event per line item? When an event has multiple recipients, the contract must serve them without dumping the entire object graph.

### `eventId` Differs from `aggregateId`

~~~text
OrderPlaced(eventId=E1, orderId=ORD-344, version=1)
OrderPaid(eventId=E2, orderId=ORD-344, version=2)
Retry OrderPlaced(eventId=E1, orderId=ORD-344, version=1)
~~~

The consumer should process E1 and E2, and discard the retried E1. Deduplicating by `orderId` would accidentally drop E2 as well.

### How to Evolve Schemas

- Add optional fields with defaults and ensure older consumers ignore unknown fields when permitted by contract.
- When semantics or required fields change, consider `OrderPlacedV2` or a planned `schemaVersion` bump.
- Run contract tests for producer/consumer when deploying independently.
- Events still sitting in the outbox or DLQ must remain deserializable after a new deployment.
- The **event contract** version differs from the **JPA entity** version or database migration version.

## 6. Designing the Outbox Table in Two Different Ways

### 6.1. Polling Outbox Schema

A general schema for JDBC polling:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(24) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE integration_outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INT NOT NULL,
    payload_json VARCHAR(4000) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    next_retry_at TIMESTAMP NULL,
    published_at TIMESTAMP NULL,
    attempts INT NOT NULL DEFAULT 0
);

CREATE INDEX ix_integration_outbox_pending
    ON integration_outbox(status, next_retry_at, created_at);
~~~

This is an **illustrative polling schema**, not fully portable SQL or Debezium's default schema. PostgreSQL can use `uuid`, `jsonb`, `timestamptz`, and partial indexes; MySQL/H2 differ. `status` can include:

~~~text
PENDING -> PROCESSING -> SENT
                  |
                  +-> RETRY_PENDING -> PROCESSING
                  |
                  +-> FAILED_PERMANENT / QUARANTINED
~~~

With multiple workers, add `locked_by`, `lease_until`, `next_retry_at`, and an atomic claim strategy.

### 6.2. Schema for Debezium Outbox Event Router

When choosing **CDC** via Debezium, note that the **Outbox Event Router SMT** expects these default columns:

~~~sql
-- Illustrative schema for PostgreSQL + Debezium Outbox SMT:
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregatetype VARCHAR(255) NOT NULL,
    aggregateid VARCHAR(255) NOT NULL,
    type VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL
);
~~~

Under default settings, `id` goes into message headers, `aggregateid` becomes the message key, `aggregatetype` routes the topic, `type` is the event type, and `payload` is the message payload. Other fields can be mapped using SMT options such as `table.field.event.id`, `table.field.event.key`, and `table.field.event.payload`.

**Important:** Debezium's Outbox Router documentation notes that an SMT outbox table **expects INSERTed event rows**, not a polling-style UPDATE status workflow. Updates are treated as invalid operations under default SMT policy. For CDC, design the schema and cleanup for Debezium/the connector; do not port polling's `UPDATE status='SENT'` onto a CDC table expecting compatibility.

### 6.3. Choosing the Schema by Relay Strategy

**Choose polling** when you want an application worker managing retries, backoff, and status using only an RDBMS. **Choose CDC** when you already run Kafka Connect/Debezium and want to tail the DB transaction log; the platform must manage connector offsets, log retention, and deployment. Both require consumer-side deduplication.

Never run **both polling and CDC emitting the same rows** to the same topic without explicit ownership and deduplication; it easily causes double-publishing.

## 7. Atomic Write in Spring: The Most Critical Spot

The clearest approach is writing the business row and the integration outbox row **inside the same transactional method**:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orderRepository;
    private final IntegrationOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orderRepository,
            IntegrationOutboxRepository outbox) {
        this.orderRepository = orderRepository;
        this.outbox = outbox;
    }

    @Transactional
    public void place(CreateOrder command) {
        Order order = orderRepository.create(command);
        IntegrationEvent event = IntegrationEvent.orderPlaced(order);
        outbox.insert(event);
    }
}
~~~

This is an **integration snippet**, requiring definitions for repositories, event factory, transaction manager, and serializer. To genuinely guarantee atomicity:

1. `place(...)` must be invoked through the Spring transactional proxy or a real programmatic transaction.
2. Both repositories must use **the same DB/resource managed by the transaction manager**.
3. The outbox `INSERT` runs **before T1 commits**, not inside `AFTER_COMMIT`.
4. If the outbox `INSERT` fails, the transaction must roll back the business change as well.
5. If code catches the outbox exception and still commits, the entire invariant is broken.
6. If business data lives in DB A and the outbox lives in DB B without a coordinator, it is still a dual write.

### Do Not Persist the Initial Integration Outbox Row in `AFTER_COMMIT`

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void writeOutbox(OrderPlaced domainEvent) {
    outboxRepository.insert(domainEvent);
}
~~~

This is a **counter-example** when the goal is an atomic outbox. When the callback runs, business T1 has already committed. Opening `REQUIRES_NEW` to insert the outbox creates an independent T2; the JVM can still die between T1 and T2. Without opening T2, reusing old resources during transaction completion may never commit the insert.

`@TransactionalEventListener(AFTER_COMMIT)` is useful for post-commit side effects, yet **does not create durability**. When an event must exist whenever T1 commits, write the outbox directly inside T1.

### What About Using a Plain `@EventListener` to Write the Outbox?

Possible, provided you ensure the listener runs **synchronously** in **the same T1** and an outbox exception rolls back the transaction. If a multicaster executor or `@Async` is ever enabled, the outbox write can split into another thread/transaction and break atomicity. Because the outbox is a core invariant, an **explicit** outbox repository call inside the service/domain unit of work is usually easier to audit.

## 8. Runnable Example: Java 17 + Spring Framework 6.2 + JDBC/H2

This program demonstrates a **minimal design** covering these branches:

1. Producer writes order and outbox **in the same T1**, then commits.
2. Producer intentionally throws an exception after both INSERTs in T2; both INSERTs roll back.
3. Relay sends the event **without marking `SENT`**, simulating a crash between broker send and DB acknowledgment.
4. Relay runs again, sending **the exact same `eventId`**. The in-memory consumer deduplicates, applying it only once.
5. Relay marks `SENT`; the program reads back row counts from H2.

No real Kafka is needed to demonstrate transaction atomicity and the crash window. The broker in the demo is a synchronous stub. Production multi-worker relays and durable inboxes are covered in later sections.

### 8.1. Project Structure

~~~text
integration-event-outbox/
├── pom.xml
└── src/main/java/demo/IntegrationOutboxDemo.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>integration-event-outbox</artifactId>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. src/main/java/demo/IntegrationOutboxDemo.java

~~~java
package demo;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class IntegrationOutboxDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderWriter producer = context.getBean(OrderWriter.class);

            jdbc.execute("CREATE TABLE orders (" +
                "order_id VARCHAR(64) PRIMARY KEY, state VARCHAR(24) NOT NULL)");

            jdbc.execute("CREATE TABLE integration_outbox (" +
                "event_id VARCHAR(64) PRIMARY KEY, " +
                "aggregate_id VARCHAR(64) NOT NULL, " +
                "aggregate_version BIGINT NOT NULL, " +
                "event_type VARCHAR(100) NOT NULL, " +
                "schema_version INT NOT NULL, " +
                "payload_json VARCHAR(2000) NOT NULL, " +
                "status VARCHAR(20) NOT NULL, " +
                "created_at TIMESTAMP NOT NULL)");

            // T1: business + integration event commit together.
            producer.place("ORD-344", "EVT-344", false);
            printState("after commit", jdbc);

            // T2: intentionally roll back both business + outbox.
            try {
                producer.place("ORD-ROLLBACK", "EVT-ROLLBACK", true);
            } catch (IllegalStateException e) {
                System.out.println("rollback cause=" + e.getMessage());
            }
            printState("after rollback", jdbc);

            CountingConsumer consumer = new CountingConsumer();
            LocalBroker broker = new LocalBroker(consumer);
            PollingRelay relay = new PollingRelay(jdbc, broker);

            // Attempt 1: sent successfully but not yet marked SENT.
            relay.sendNext(false);
            System.out.println("simulated relay crash before marking SENT");

            // Attempt 2: retry old eventId; consumer must deduplicate.
            relay.sendNext(true);

            System.out.println("final orders=" + ordersCount(jdbc) +
                " pending=" + outboxCount(jdbc, "PENDING") +
                " sent=" + outboxCount(jdbc, "SENT") +
                " consumerApplied=" + consumer.applied());
        }
    }

    private static int ordersCount(JdbcTemplate jdbc) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders", Integer.class);
        return result == null ? 0 : result;
    }

    private static int outboxCount(JdbcTemplate jdbc, String status) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM integration_outbox WHERE status=?",
            Integer.class, status);
        return result == null ? 0 : result;
    }

    private static void printState(String label, JdbcTemplate jdbc) {
        System.out.println(label + " orders=" + ordersCount(jdbc) +
            " pending=" + outboxCount(jdbc, "PENDING"));
    }

    public record IntegrationMessage(
        String eventId, String aggregateId,
        String eventType, String payloadJson) {
    }

    // Not final so Spring can use a class-based transaction proxy.
    public static class OrderWriter {
        private final JdbcTemplate jdbc;

        public OrderWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void place(String orderId, String eventId, boolean forceFail) {
            jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "PLACED");

            // Demo uses a constant payload; production uses a JSON serializer.
            String payload = "{\"state\":\"PLACED\"}";

            jdbc.update(
                "INSERT INTO integration_outbox (" +
                "event_id, aggregate_id, aggregate_version, " +
                "event_type, schema_version, payload_json, " +
                "status, created_at) " +
                "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', CURRENT_TIMESTAMP)",
                eventId, orderId, 1L, "OrderPlaced", 1, payload);

            if (forceFail) {
                throw new IllegalStateException("simulated rollback");
            }
        }
    }

    // Only simulates an in-JVM consumer; not durable across restarts.
    public static class CountingConsumer {
        private final Set<String> seenIds = new HashSet<>();
        private int applied;

        public void handle(IntegrationMessage message) {
            if (!seenIds.add(message.eventId())) {
                System.out.println(
                    "consumer duplicate event_id=" + message.eventId());
                return;
            }
            applied++;
            System.out.println(
                "consumer applied event_id=" + message.eventId());
        }

        public int applied() {
            return applied;
        }
    }

    // Stub, NOT equivalent to a real broker with durability/acks.
    public static class LocalBroker {
        private final CountingConsumer consumer;

        public LocalBroker(CountingConsumer consumer) {
            this.consumer = consumer;
        }

        public void publish(IntegrationMessage message) {
            System.out.println(
                "broker published event_id=" + message.eventId());
            consumer.handle(message);
        }
    }

    // Single relay for demo; no multi-worker locking/leasing.
    public static class PollingRelay {
        private final JdbcTemplate jdbc;
        private final LocalBroker broker;

        public PollingRelay(JdbcTemplate jdbc, LocalBroker broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public boolean sendNext(boolean acknowledge) {
            List<IntegrationMessage> records = jdbc.query(
                "SELECT event_id, aggregate_id, event_type, payload_json " +
                "FROM integration_outbox WHERE status='PENDING' " +
                "ORDER BY created_at, event_id LIMIT 1",
                (rs, index) -> new IntegrationMessage(
                    rs.getString("event_id"),
                    rs.getString("aggregate_id"),
                    rs.getString("event_type"),
                    rs.getString("payload_json"))
            );

            if (records.isEmpty()) {
                return false;
            }

            IntegrationMessage message = records.get(0);
            broker.publish(message);

            if (acknowledge) {
                int affected = jdbc.update(
                    "UPDATE integration_outbox SET status='SENT' " +
                    "WHERE event_id=? AND status='PENDING'",
                    message.eventId());
                if (affected != 1) {
                    throw new IllegalStateException("ack conflict");
                }
            }
            return true;
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:integration_outbox_344;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public OrderWriter orderWriter(JdbcTemplate jdbc) {
            return new OrderWriter(jdbc);
        }
    }
}
~~~

### 8.4. Running

From the `integration-event-outbox` directory, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.IntegrationOutboxDemo
~~~

Lines printed by the program code (Maven/Spring/H2 logs may vary):

~~~text
after commit orders=1 pending=1
rollback cause=simulated rollback
after rollback orders=1 pending=1
broker published event_id=EVT-344
consumer applied event_id=EVT-344
simulated relay crash before marking SENT
broker published event_id=EVT-344
consumer duplicate event_id=EVT-344
final orders=1 pending=0 sent=1 consumerApplied=1
~~~

### 8.5. Analyzing the Output

**T1 commit:** `OrderWriter` is a Spring bean, `place(...)` is invoked through the transaction proxy, and `JdbcTemplate` uses the same `DataSource`. Both INSERTs into `orders` and `integration_outbox` share T1. After commit, there is one order and one `PENDING` outbox row.

**T2 rollback:** the service INSERTs a new order and event, then throws `IllegalStateException`. The unchecked exception rolls back T2 under default rules; both tables still contain only the rows from T1.

**Crash gap attempt 1:** the relay reads the `PENDING` outbox row and the stub broker delivers it to the consumer. Because `acknowledge=false`, the DB status is not updated. This is an **intentional simulation**; the demo process does not actually terminate.

**Retry attempt 2:** the same row and the same `eventId=EVT-344` are re-sent. The consumer uses a `Set` to discard duplicates; the result is `consumerApplied=1` even though the broker published twice. The relay marks `SENT`.

### Clear Limitations of the Demo

- `LocalBroker` is not Kafka/RabbitMQ/an HTTP client and has no broker durability or real ACKs.
- The consumer's `HashSet` **loses state on restart**; production requires a durable inbox or unique constraint.
- The relay has only one worker and no claim/lease mechanism; **do not deploy as-is across multiple replicas**.
- There is no exponential backoff, DLQ, batch processing, quarantine, message authentication, schema registry, or CDC.
- `OrderWriter` uses caller-supplied fixed `eventId` values for deterministic output. Production requires a unique ID per event occurrence (typically UUID/ULID per policy).
- Constant JSON payload is for demo only; production must use a tested serializer rather than concatenating JSON from inputs.

The takeaway from the example is **not exactly-once delivery**, rather: local transactions protect business/outbox atomicity; **retries can duplicate**, so consumers need idempotency.

## 9. Designing a Polling Relay in Production

A relay needs a state machine, atomic claiming, and recovery:

~~~text
OUTBOX PENDING
   |
   +-- Short worker claim, set PROCESSING + lease
   |
   +-- Call broker producer and await ACK
        |
        +-- Success -> UPDATE SENT
        |
        +-- Transient error -> attempts++, next_retry_at, RETRY_PENDING
        |
        +-- Permanent error -> QUARANTINED / DLQ + alert
        |
        +-- Worker crash -> lease expires, another worker reclaims
~~~

Never run two workers executing the same `SELECT PENDING` query and sending without locking. Two workers can **send the same message** before either updates the status.

### Claiming with PostgreSQL (DB-Specific)

**PostgreSQL-specific conceptual example**:

~~~sql
BEGIN;
SELECT event_id
FROM integration_outbox
WHERE status = 'PENDING'
ORDER BY created_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 100;

-- For the selected events, UPDATE to PROCESSING and set a lease.
-- Commit the claim transaction before calling the broker.
COMMIT;
~~~

Syntax and clause ordering must be verified against your PostgreSQL/database version; this is a design illustration, **not a complete migration**. In production, pick tested claim SQL—such as `FOR UPDATE SKIP LOCKED` or conditional UPDATE/optimistic locking—with appropriate indexes.

**Do not hold a DB row-locking transaction open across a slow network call.** Claim in a short transaction, commit the claim, call the broker, and then update the outcome in another transaction. Between broker ACK and `UPDATE SENT` a crash gap remains: when uncertain whether it was sent, **retry with the same `eventId`**. That is intentional at-least-once semantics.

### Leases and Retries

A `PROCESSING` record needs `lease_until`; if a worker dies, a job manager returns it to a claimable state. Handle the case where a lease expires while the original worker is still sending, causing a duplicate send—consumers must still deduplicate.

A retry policy should include:

- **Timeouts** on broker/API sends, distinguishing timeouts from definitive errors.
- **Exponential backoff + jitter**, curbing thundering herds when the broker recovers.
- **Maximum attempts or time budget** with a quarantine/DLQ policy for permanent errors.
- **Bounded last-error classes** for metrics; log stack traces with controls.
- **Idempotent replay** keeping the original `eventId`; never mint a new ID for retries.
- **Manual replay tooling** with auditing and authorization to avoid bulk-replaying emails or payments accidentally.

An alert on "`oldest PENDING age` exceeds SLO" is far more informative than watching total row counts alone.

## 10. CDC/Debezium When Reading the Commit Log

Instead of polling a table, **change data capture (CDC)** reads committed record changes from the DB transaction log. **Debezium Outbox Event Router** transforms outbox INSERTs into Kafka messages.

One architecture:

~~~text
T1 COMMIT:
  business change + outbox INSERT
          |
       DB WAL / binlog
          |
   Debezium source connector
          |
   Outbox Event Router SMT
          |
      Kafka topic
          |
       Consumer
~~~

Debezium documentation specifies defaults:

- `id` becomes the event ID in message headers.
- `aggregatetype` routes to the topic.
- `aggregateid` becomes the message key, useful for partition ordering.
- `type` is the event type.
- `payload` is the event content.

If your schema differs from defaults, configure SMT mappings. Fields such as `schemaVersion`, correlation, or tenant can be placed in additional headers or the envelope while managing compatibility.

**Never combine a polling mutable-status table and a CDC insert-only schema** without an explicit design. Debezium Outbox Router expects outbox events to be INSERTed; updating an outbox row is an unexpected operation. CDC has its own offset/snapshot/log-retention mechanics; downstream consumers still need consumer idempotency.

### Choosing Between Polling and CDC

| Factor | Polling | CDC |
|---|---|---|
| Infrastructure | RDBMS + worker | RDBMS log capture + connector + broker |
| Detection latency | Per poll interval | Near real-time |
| Multi-worker claiming | Managed by worker | Managed via connector/offsets |
| Retry state | `status/attempts/lease` in DB | Connector/broker retry semantics |
| Schema | Can be mutable | Should align with SMT/insert-only |
| DB impact | Queries and locks/indexes | Log streaming and retention |
| Best fit | Small-to-medium systems wanting simple control | Organizations already operating a CDC platform |

Neither automatically solves exactly-once **business effects** at the consumer.

## 11. Consumer Idempotency with a Durable Inbox

The demo uses a `HashSet` for illustration; production must assume:

1. The consumer applied event E1 successfully.
2. The consumer crashed before ACKing the broker.
3. The broker redelivers E1 after restart.
4. The consumer must not apply the side effect a second time.

Inbox table:

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(64) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

A consumer transaction:

~~~text
BEGIN T3
   INSERT processed_integration_events(consumer_name, event_id)
   - if duplicate key -> already processed, skip side effect
   UPDATE inventory_projection ...
COMMIT T3
ACK broker delivery
~~~

**The processed marker and the business DB mutation must commit atomically in the same T3.** If the marker is committed first and the process crashes before applying the business effect (in a separate T4), retries will wrongly skip it and lose the effect.

PostgreSQL example:

~~~sql
INSERT INTO processed_integration_events(
    consumer_name, event_id, processed_at
) VALUES ('inventory', :eventId, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

This SQL is PostgreSQL-specific; the consumer checks affected rows. If 0, it is a duplicate and can be ACKed per policy; if 1, proceed with the business update in the same transaction. Never ACK the message before T3 commits. If T3 commits and the broker ACK fails, the message may return; the inbox skips the duplicate.

### What If the Side Effect Is an Email or External API Outside the Database?

No local DB transaction makes sending an email or HTTP request atomic with the marker. You need downstream API idempotency keys, an outbox in the consumer service, durable job status, or compensation. **Never claim exactly-once side effects** simply because a processed-events table exists.

## 12. Ordering: When an Aggregate Emits Multiple Events

Suppose an order has:

~~~text
OrderPlaced(orderId=ORD-344, version=1, eventId=E1)
OrderPaid(orderId=ORD-344, version=2, eventId=E2)
OrderShipped(orderId=ORD-344, version=3, eventId=E3)
~~~

To preserve meaningful order:

- Use `aggregateId` as the Kafka message key so events for the same aggregate generally land in the same partition.
- Assign `aggregateVersion` via optimistic locking or a sequence mechanism inside the transaction.
- The relay must consider send ordering across multiple instances, retries, and leases; `ORDER BY created_at` **does not prove commit order** because transactions can commit in a different order than row creation.
- Consumers must guard against stale/out-of-order events using versions and business invariants.
- If a stream has non-contiguous versions due to filtering event types, **do not** enforce `incomingVersion == current+1` for every event.

Example logic suited to a **contiguous version stream**:

~~~text
incomingVersion <= lastAppliedVersion -> duplicate / stale
incomingVersion == lastAppliedVersion + 1 -> apply
incomingVersion > lastAppliedVersion + 1 -> gap: buffer/retry/resync
~~~

If the aggregate version increments in transactions that do not emit integration events, use another ordering contract (a dedicated event sequence, lookup/resync). Never assume UUIDs, timestamps, or DB auto-increment IDs always reflect absolute commit order under all conditions.

## 13. Where Should `@EventListener`, `@TransactionalEventListener`, and Spring Modulith Be Used?

### `@EventListener` for Internal Domain Logic

A domain event can trigger handlers in the same process. If you want a synchronous `@EventListener` to write an outbox **within T1**, you must ensure the publisher is truly inside T1, the listener is not `@Async`, the multicaster does not switch threads, and exceptions are not swallowed. That is a lot of assumptions to guard.

For mandatory integration events, **writing the outbox directly inside the application service/unit of work** is usually easier to review and test for atomicity.

### `@TransactionalEventListener(AFTER_COMMIT)` Is Not the Initial Outbox Writer

Do not write the outbox for the first time after the aggregate commits and expect atomicity. An `AFTER_COMMIT` callback still has a crash gap between T1 and T2. Use it for non-durable tasks or as a wake-up signal for the relay, while ensuring **the relay always polls the durable outbox** rather than relying solely on an in-memory wake-up event.

A sound optimization:

~~~text
T1: write aggregate + outbox row -> COMMIT
    |
    +-- post-commit send wake-up signal to relay
    |
    +-- relay also runs a scheduled poll fallback
~~~

If the wake-up signal is lost, periodic polling still picks up committed outbox rows.

### Spring Modulith Event Publication Registry

Spring Modulith includes an **Event Publication Registry** that tracks publications for transactional event listeners, recording status so incomplete publications can be replayed depending on version and config. It is worth considering for **reliable application-module events**.

Do not equate the Modulith registry with a Kafka integration outbox: publishing across a broker still requires serializers, message keys, destinations, delivery acknowledgments, retries, and consumer idempotency. Mechanisms can be integrated with clear ownership, while avoiding double-publishing the same event to a downstream consumer.

## 14. Test Plan for an Integration Outbox Design

Testing only the happy path "one PENDING row exists" is insufficient. Tests should cover at least:

| ID | Scenario | Key assertion |
|---|---|---|
| T1 | Producer commits successfully | Order row and exact one outbox row exist with matching business fact |
| T2 | Outbox INSERT fails after order INSERT | Business write rolls back too |
| T3 | Service throws after both INSERTs | Neither order nor outbox row remains from rolled-back transaction |
| T4 | JVM crashes after commit before relay | New relay reads the `PENDING` outbox row |
| T5 | Broker send succeeds but marking `SENT` did not run | Re-sends same `eventId`; consumer does not reapply |
| T6 | Two relay workers claim concurrently | Row claimed via lock/lease per policy |
| T7 | Retry hits network timeout | Backs off; does not mark `SENT` prematurely |
| T8 | Consumer ACK fails after T3 commits | Redelivery is deduplicated by inbox |
| T9 | Consumer receives version 3 before version 2 | Does not revert projection to stale state |
| T10 | v1 event still pending when v2 deploys | Compatible deserialization/migration |
| T11 | Prolonged broker downtime | Queue age alerts, storage capacity, and DLQ work |
| T12 | Cleanup/retention | Safely deletes/archives only `SENT`, never loses `PENDING` |
| T13 | Consumer external API idempotency | Retries do not send duplicate payments/emails |
| T14 | Multi-tenant isolation | Tenant A event cannot be processed/looked up as tenant B |

### Test Real Transactions, Not Just Mock Publishers

A fake `ApplicationEventPublisher` proves the method called `publishEvent`, yet **does not prove the outbox row committed atomically with business state**. To verify atomicity, use a Spring transaction manager and a real database or test DB with sufficiently faithful semantics.

Spring TestContext normally **rolls back `@Transactional` test methods** after the test. To assert real commits, leave the test method non-transactional and call the transactional service proxy, or explicitly use `TestTransaction.flagForCommit()` and `TestTransaction.end()` when a test-managed transaction is active.

`@RecordApplicationEvents`/`ApplicationEvents` in `spring-test` also only record events within the test; they **do not replace** asserting durable outbox rows, broker ACKs, and consumer outcomes.

## 15. Observability, SLOs, and Operations

An integration event passes through multiple milestones:

~~~text
Business COMMIT -> Outbox pending -> Relay claim
    -> Broker ACK -> Consumer received
    -> Consumer business transaction COMMIT -> ACK delivery
~~~

Each milestone should have corresponding state and metrics.

| Metric / signal | Operational meaning |
|---|---|
| `outbox.pending.count` | Number of unsent events |
| `outbox.oldest.pending.age` | Age of oldest waiting event; alerts on stuck relay |
| `outbox.relay.attempts` | Number of send attempts |
| `outbox.relay.failures` | Broker/serialization/credential errors |
| `outbox.delivery.latency` | Time from row creation to broker ACK |
| `outbox.quarantine.count` | Events that cannot be processed automatically |
| `consumer.duplicate.count` | Frequency of redelivery/deduplication |
| `consumer.processing.latency` | Downstream processing time |
| `consumer.processing.failures` | Failures after receiving message |
| `consumer.lag` | Remaining backlog in broker/partition |

Dashboards must distinguish: **producer committed**, **broker accepted**, **consumer processed**, and **business effect completed**. `status=SENT` in the outbox only means the relay believes it sent per ACK policy; it **does not** prove the consumer finished business processing.

Avoid `eventId`, `aggregateId`, email, or phone number as **low-cardinality metric tags**. Use event type, relay, outcome, and bounded error categories for metrics; `correlationId`/`traceId` can go into structured logs/traces under security policies.

### End-to-End SLOs

Example SLOs (tailored to business needs):

- 99% of integration events receive a broker ACK within an agreed window after DB commit.
- 99% finish consumer processing within another agreed window.
- No outbox row stays `PENDING` past the age threshold without alerting.
- Runbooks exist for retry storms, connector lag, poison events, and schema mismatches.

Do not set SLOs based solely on `@EventListener` duration; end-to-end integration also includes queuing, the broker, and consumers.

## 16. Security and Retention

An outbox stores data that can persist across deployments and outages, so govern it like business data:

- **Minimal payload:** do not store tokens, passwords, card numbers, or PII unless strictly required.
- **Tenant isolation:** validate `tenantId`/aggregate ownership on the consumer side; event headers do not prove authorization.
- **Encryption and DB/broker permissions:** enforce access control, key rotation, and log redaction.
- **Schema registry:** define compatibility for independently deployed producers and consumers.
- **Retention:** never delete `PENDING`/`PROCESSING` rows awaiting retry just because they are old; archive `SENT` per SLA.
- **Audited replay:** manual replays require authorization and audit trails; idempotency must outlive the possible replay window.
- **Backup/recovery:** restore business and outbox tables consistently so committed events are not lost.
- **CDC WAL/binlog:** align log retention, offset, and snapshot policies with the connector.
- **Backpressure:** during prolonged broker outages, outbox tables grow; monitor disk, index bloat, vacuum/partitioning, and throttling.

## 17. Table of Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating Spring `publishEvent` as a durable broker | Events lost on restart | Store outbox in DB |
| Sending message before DB commit | Consumer gets events for rolled-back transactions | Outbox in T1, relay after commit |
| Using only `@TransactionalEventListener(AFTER_COMMIT)` | Post-commit crash gap remains | Write durable outbox before commit |
| Writing initial outbox in `AFTER_COMMIT` | Outbox and business live in two transactions | Write together in T1 |
| Treating two datasources as one transaction | Not atomic | Put outbox in same DB or change architecture |
| Swallowing outbox INSERT exception | Business commits without event | Roll back entire unit of work |
| `@Async` writing outbox after business INSERT | Splits ThreadLocal transaction | Write synchronously in T1; relay asynchronously |
| Marking `SENT` before broker ACK | Events can be lost | Wait for proper ACK then mark; tolerate duplicates |
| Generating a new `eventId` on retry | Deduplication fails | Preserve original `eventId` on retries |
| Consumer deduplicating by `aggregateId` | Drops subsequent events for the same aggregate | Deduplicate by `eventId` |
| Inbox and projection update not atomic | Crash can cause event to be skipped | Execute in same T3 |
| Multiple relays reading `PENDING` without claim | Uncontrolled double-sends | Locks/leases/atomic claiming |
| Using `created_at` as absolute commit order | Concurrent transactions reorder | Use aggregate version and ordering contract |
| Using mutable polling schema with Debezium SMT | Unexpected UPDATE operations | Design an appropriate CDC schema |
| Looking only at `status=SENT` | Unknown whether consumer processed | Separate producer/broker/consumer metrics |
| No versioned contract | Old events become unreadable | Schema versioning and contract tests |
| Deleting `PENDING` on fixed time retention | Loses unsent events | Clean up by state and SLA |
| Assuming outbox gives exactly-once by default | Side effects can still repeat | Consumer idempotency |

## 18. Checklist for Reviewing an Outbox Pull Request

1. Is the event name business-meaningful and stable?
2. Are `eventId`/`aggregateId`/`aggregateVersion`/`schemaVersion` clearly defined?
3. Is the payload an immutable snapshot tested with the serializer?
4. Do the business row and outbox row share **the same T1/resource**?
5. Does an outbox INSERT failure roll back the business change?
6. Have self-invocation and Spring transaction proxying been checked?
7. Is the relay polling or CDC, with clear ownership and no double-publishing?
8. Are locks/leases and recovery present for multiple workers?
9. Do retries preserve `eventId`, use backoff, max attempts, and quarantine?
10. Is the broker ACK policy clear, never marking `SENT` before ACK?
11. Does the consumer have a durable inbox and idempotent side effects?
12. Is there a per-aggregate ordering/versioning policy?
13. Are schema evolution and replaying old events tested?
14. Are backlog age, retries, failures, duplicates, and consumer outcomes instrumented?
15. Are PII/tenant protections, retention/cleanup, and replay authorization in place?
16. Are there fault-injection tests for rollback, crash gaps, duplicates, and concurrent claims?

## 19. Conclusion and References

**Designing an outbox for integration events** is more than adding an `outbox_events` table. It is an end-to-end contract:

The **producer** writes business state + event record in **the same local transaction**, the **relay** delivers committed events to the broker with retries and crash recovery, the **consumer** applies idempotency inside its own transaction, and **operations** monitor latency, backlogs, errors, schema evolution, and replays.

In Spring, `@EventListener` works well for internal domain events and `@TransactionalEventListener(AFTER_COMMIT)` helps pick the execution phase, yet **neither replaces an atomic outbox INSERT in T1**. Choose polling or Debezium CDC based on infrastructure, and keep the two schemas distinct. An outbox provides **at-least-once delivery**; achieving "once-only" business effects additionally requires stable `eventId`s, inbox/idempotency, ordering, and appropriate side-effect rules.

### Official / Reference Documentation

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): semantics of `@TransactionalEventListener`.
- [Spring Framework Reference — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction proxies, propagation, rollback rules.
- [Debezium — Outbox Event Router SMT](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): default schema, key/header/topic routing, INSERT-only expectation.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): Event Publication Registry and incomplete event publications.
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): dual writes, relays, delivery semantics.
- [PostgreSQL Documentation — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE` and `SKIP LOCKED` when designing polling workers.
