# Events and the Outbox Pattern in Spring Framework Application Events

## 1. The Problem: Reliability When Publishing Events Outside the Process

In Spring, `ApplicationEventPublisher.publishEvent(...)` and `@EventListener` help decouple business processing modules. A service can save an order, publish `OrderPlaced`, and let listeners send emails, update search indexes, or integrate with another system. However, **Spring Application Events is not a durable message queue**: events are primarily dispatched inside the JVM, and Spring Framework does not automatically persist a record that can be replayed after a crash.

Familiar example:

~~~java
@Transactional
public void placeOrder(String orderId) {
    orderRepository.insert(orderId);
    eventPublisher.publishEvent(new OrderPlaced(orderId));
}
~~~

This is an integration snippet, not a standalone program. You must have the corresponding `OrderPlaced`, repository, publisher, and Spring transaction manager.

If a listener sends a message to Kafka or an HTTP API, the program needs **two independent changes**: committing the DB and sending the message. They do not automatically become a single atomic transaction just because the method is annotated with `@Transactional`. This is the **dual-write problem**.

There are two easy-to-get-wrong orderings:

- **Send the message before DB commit:** the broker receives `OrderPlaced`, and then the DB rolls back. Consumers may believe the order exists even though no row actually committed.
- **Commit the DB first, send the message after:** the DB already holds the order, yet the JVM crashes before sending. Consumers never hear about the change.

The **Transactional Outbox Pattern** replaces direct message sending with **INSERTing an outbox record in the same local database transaction as the business data**. After commit, a separate relay delivers the outbox to the broker. If the process dies, the outbox row remains and can be resent.

> Core guarantee: the business update and outbox event **commit together or roll back together**. The relay normally delivers using an *at least once* model, so consumers must tolerate duplicates. An outbox does not by itself promise *exactly once end-to-end*.

### Lesson Objectives

1. Understand why `@EventListener` and `@TransactionalEventListener(AFTER_COMMIT)` do not automatically solve dual-write durability.
2. Design a transaction covering both the business row and the outbox row.
3. Build a crash-recoverable polling relay/CDC publisher.
4. Use `eventId` and an inbox/idempotency to handle duplicates properly.
5. Manage ordering/versioning, retries, schemas, security, and observability.
6. Run a Java 17 + Spring JDBC + H2 example demonstrating commit, rollback, and resend after a crash gap.
7. Distinguish Spring Modulith's Event Publication Registry from a broker-integrated outbox.

## 2. Failure Matrix: What Happens If a Crash Occurs at Each Point?

Suppose we want to create order `ORD-295` and notify the inventory system. Scenarios:

| Failure point | With direct send | With transactional outbox |
|---|---|---|
| Failure before DB commit | Event may already be sent even though DB rolls back | Outbox row also rolls back |
| DB commit succeeds, crash before send | Event may be lost permanently | Committed outbox row remains for relay |
| Relay reads row but broker is temporarily down | No durable retry if using only an in-memory callback | Row awaits retry with attempts/backoff |
| Broker receives but producer misses ack | Resending may create duplicates | Relay resends same eventId; consumer deduplicates |
| Worker crash after send before marking SENT | Unclear whether sent or not | Row stays pending/lease expires, retried |
| Consumer receives message twice | Side effect may repeat | Idempotent consumer prevents repetition by eventId |

### Crash Gap in AFTER_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendToBroker(OrderPlaced event) {
    broker.send(event);
}
~~~

This is illustrative code. `AFTER_COMMIT` only ensures the callback is scheduled in the phase after the source transaction commits; it **does not persist the event before commit**. If a crash occurs after commit but before the callback, the message can still be lost. If the callback throws an exception, the business row has already committed and you cannot roll back the source transaction by throwing in this phase.

**Conclusion:** `AFTER_COMMIT` is an **execution phase**, not a durable outbox.

## 3. Transactional Outbox Architecture

~~~text
Client / HTTP request
        |
        v
Spring OrderService.placeOrder()
        |
        +-- BEGIN T1 (local JDBC/JPA transaction)
        |      |
        |      +-- INSERT/UPDATE orders
        |      |
        |      +-- INSERT outbox_events
        |      |
        |      +-- COMMIT T1
        |            |
        |            +-- If rolled back: both changes disappear
        |
        v
Database: orders + outbox_events (durable)
        |
        +--> Polling relay or Debezium CDC
                  |
                  +-- claim/read committed events
                  +-- send to broker, wait for ack
                  +-- retry on error
                  |
                  v
             Broker / API
                  |
                  v
            Consumer service
                  |
                  +-- deduplicate eventId in durable inbox
                  +-- apply business side effect
                  +-- ack message
~~~

There are three units of responsibility:

**Producer transaction** writes the aggregate and outbox **into the same physical transaction and the same database/resource**. That is where atomicity comes from. If the business DB is A while the outbox sits in DB B without a transaction coordinator, the dual-write problem remains.

**Relay** forwards committed events to the broker/API; it must handle transient errors, process restarts, multi-worker locks/leases, retries, and cleanup. The relay is not a business component responsible for deciding whether an order is valid.

**Consumer** validates the event contract, prevents duplicates, and handles ordering and side effects in its own transaction. A message acknowledged by the broker does not prove the consumer succeeded.

## 4. Designing the Outbox Schema

Illustrative polling tables:

~~~sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INT NOT NULL,
    payload_json VARCHAR(4000) NOT NULL,
    status VARCHAR(16) NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    next_retry_at TIMESTAMP NULL,
    published_at TIMESTAMP NULL
);

CREATE INDEX idx_outbox_status_retry
    ON outbox_events(status, next_retry_at, created_at);
~~~

This is an example schema to explain polling. Production DBs may use `UUID`, `JSONB`, `CLOB`, timestamp with time zone, partitioning, or different indexes. Design based on throughput, retention, query plans, and the real SQL dialect.

| Column | Meaning |
|---|---|
| `event_id` | ID of **one event occurrence**, used for deduplication |
| `aggregate_type` | Source kind, e.g., `Order` |
| `aggregate_id` | Business object key; can serve as partition key |
| `aggregate_version` | Aggregate version, useful for ordering |
| `event_type` | `OrderPlaced`, `OrderPaid`, etc. |
| `schema_version` | Payload structure version |
| `payload_json` | Minimal serializable event snapshot/delta |
| `status` | `PENDING`/`PROCESSING`/`SENT` for polling |
| `attempts` and `next_retry_at` | Retry history and next attempt time |
| `created_at` | Row creation time, not guaranteed to be commit sequence |
| `published_at` | Relay confirmed sent, not synonymous with consumer completion |

A reference event payload:

~~~json
{
  "eventId": "16d9e1e5-a625-4bcb-9223-5d127c7b91db",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "ORD-295",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T06:40:00Z",
  "data": {
    "state": "PLACED",
    "currency": "VND",
    "totalMinorUnits": 350000
  }
}
~~~

This is sample data. `occurredAt` does not prove absolute DB commit order. Avoid using `entity.toString()`, JPA proxies, or unnecessary secrets/PII as payloads. Fields a consumer needs as of **when the event occurred** should be an immutable snapshot rather than just an entity ID if re-reading the DB later could see a different version.

### Distinguishing eventId and aggregateId

`ORD-295` can emit multiple events:

~~~text
OrderPlaced(eventId=E1, aggregateId=ORD-295)
OrderPaid(eventId=E2, aggregateId=ORD-295)
OrderShipped(eventId=E3, aggregateId=ORD-295)
Retry OrderPaid(eventId=E2, aggregateId=ORD-295)
~~~

Consumers must accept `E1`, `E2`, `E3`; the repeated `E2` is skipped. If you deduplicate by `aggregateId`, the system will wrongly discard every event after the first one for that order. Retries **preserve the same eventId**; a new business event requires a new `eventId`.

## 5. Writing the Outbox in the Business Transaction in Spring

The clearest pattern is writing both rows directly inside a Spring transactional service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders, OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void place(CreateOrder command) {
        Order order = orders.create(command);
        outbox.insert(new OutboxMessage(
            UUID.randomUUID(),
            "Order",
            order.id(),
            order.version(),
            "OrderPlaced",
            1,
            serialize(order)
        ));
    }
}
~~~

This is **illustrative integration code**, requiring definitions for the classes, serializer, repositories, transaction manager, and imports. Within one unit of work:

- If `orders.create` fails, the outbox does not commit.
- If `outbox.insert` fails and the exception rolls back the transaction, the order does not commit.
- If the transaction commits successfully, **both rows durably exist together**.
- The relay sends after commit; it does not depend on whether the request thread stays alive.

### Do Not Move the Outbox INSERT to AFTER_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    outbox.insert(event); // Not inside the already-committed T1.
}
~~~

This is a **counterexample for atomic outbox**. When the callback runs, the transaction has already committed. A `REQUIRES_NEW` here merely starts an independent T2; crashing between T1 and T2 still loses the event. Using the old transaction's resource in completion may leave the write without a subsequent commit. The outbox row must be written **before T1 commits**.

### Can a Regular @EventListener Write the Outbox?

Yes, if the `@EventListener` is **truly synchronous** and `outbox.insert` participates in **the exact T1**, with the event published while T1 is still open. However, you must verify that the bean is invoked, the multicaster does not switch threads, exceptions are not swallowed by an `ErrorHandler`, and the transaction manager binds the right resource.

For mandatory reliability invariants, calling an outbox writer directly from the service or domain unit of work is usually **easier to prove and test** than a dispatch path that could later be configured asynchronously.

## 6. Runnable Example: Java 17 / Maven / Spring JDBC / H2

The example runs two transactions, then simulates a relay sending one message successfully and crashing before marking it SENT. A simple consumer uses `eventId` to skip the duplicate.

**Purpose:** illustrate atomic writes, rollbacks, and at-least-once/deduplication. `StubBroker` is not real Kafka; the consumer's `HashSet` only holds in-memory state. This code does not replace a multi-worker production design.

Structure:

~~~text
outbox-demo/
├── pom.xml
└── src/main/java/demo/OutboxDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>outbox-demo</artifactId>
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

### src/main/java/demo/OutboxDemo.java

~~~java
package demo;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

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

public final class OutboxDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OrderService service = ctx.getBean(OrderService.class);

            jdbc.execute("CREATE TABLE orders (" +
                "id VARCHAR(64) PRIMARY KEY, state VARCHAR(20) NOT NULL)");

            jdbc.execute("CREATE TABLE outbox_events (" +
                "event_id VARCHAR(36) PRIMARY KEY, " +
                "aggregate_id VARCHAR(64) NOT NULL, " +
                "event_type VARCHAR(64) NOT NULL, " +
                "payload_json VARCHAR(1024) NOT NULL, " +
                "status VARCHAR(16) NOT NULL, " +
                "created_at TIMESTAMP NOT NULL)");

            // Both INSERTs commit together in T1.
            service.createOrder("ORD-295", false);
            printState("after commit", jdbc);

            // Both INSERTs roll back together in T2.
            try {
                service.createOrder("ORD-ROLLBACK", true);
            } catch (IllegalStateException e) {
                System.out.println("rollback cause=" + e.getMessage());
            }
            printState("after rollback", jdbc);

            Consumer consumer = new Consumer();
            BrokerStub broker = new BrokerStub(consumer);
            Relay relay = new Relay(jdbc, broker);

            // Simulate a crash after broker send but before outbox ack.
            relay.sendNext(false);
            System.out.println("simulated crash before ack");

            // Retry with the exact same old eventId; consumer deduplicates.
            relay.sendNext(true);

            System.out.println("final: pending=" + count(jdbc, "PENDING") +
                " sent=" + count(jdbc, "SENT") +
                " applied=" + consumer.appliedCount());
        }
    }

    private static void printState(String label, JdbcTemplate jdbc) {
        Integer orders = jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders", Integer.class);
        System.out.println(label + ": orders=" + orders +
            " pending=" + count(jdbc, "PENDING"));
    }

    private static int count(JdbcTemplate jdbc, String status) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM outbox_events WHERE status=?",
            Integer.class, status);
        return value == null ? 0 : value;
    }

    public record OutboxRow(
            String eventId, String aggregateId,
            String eventType, String payloadJson) {
    }

    // Non-final class so Spring's class-based proxy works.
    public static class OrderService {
        private final JdbcTemplate jdbc;

        public OrderService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void createOrder(String id, boolean fail) {
            jdbc.update("INSERT INTO orders(id, state) VALUES (?, ?)",
                id, "PLACED");

            // Fixed payload for demo; production uses a JSON serializer.
            String payload = "{\"state\":\"PLACED\"}";

            jdbc.update(
                "INSERT INTO outbox_events " +
                "(event_id, aggregate_id, event_type, " +
                "payload_json, status, created_at) " +
                "VALUES (?, ?, ?, ?, 'PENDING', CURRENT_TIMESTAMP)",
                UUID.randomUUID().toString(), id, "OrderPlaced", payload);

            if (fail) {
                throw new IllegalStateException("force rollback");
            }
        }
    }

    // Synchronous broker stub, used only for observing the demo.
    public static class BrokerStub {
        private final Consumer consumer;

        public BrokerStub(Consumer consumer) {
            this.consumer = consumer;
        }

        public void send(OutboxRow row) {
            System.out.println("broker delivered type=" +
                row.eventType() + " aggregate=" + row.aggregateId());
            consumer.receive(row);
        }
    }

    // Consumer Set is example-only: restarts lose deduplication state.
    public static class Consumer {
        private final Set<String> processed = new HashSet<>();
        private int applied;

        public void receive(OutboxRow row) {
            if (!processed.add(row.eventId())) {
                System.out.println("consumer duplicate skipped aggregate=" +
                    row.aggregateId());
                return;
            }
            applied++;
            System.out.println("consumer applied aggregate=" +
                row.aggregateId());
        }

        public int appliedCount() {
            return applied;
        }
    }

    // Single-worker relay: no atomic claim/lease yet.
    public static class Relay {
        private final JdbcTemplate jdbc;
        private final BrokerStub broker;

        public Relay(JdbcTemplate jdbc, BrokerStub broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public boolean sendNext(boolean acknowledge) {
            List<OutboxRow> pending = jdbc.query(
                "SELECT event_id, aggregate_id, event_type, payload_json " +
                "FROM outbox_events WHERE status='PENDING' " +
                "ORDER BY created_at, event_id LIMIT 1",
                (rs, index) -> new OutboxRow(
                    rs.getString("event_id"),
                    rs.getString("aggregate_id"),
                    rs.getString("event_type"),
                    rs.getString("payload_json"))
            );
            if (pending.isEmpty()) {
                return false;
            }

            OutboxRow row = pending.get(0);
            broker.send(row);

            if (acknowledge) {
                int changed = jdbc.update(
                    "UPDATE outbox_events SET status='SENT' " +
                    "WHERE event_id=? AND status='PENDING'",
                    row.eventId());
                if (changed != 1) {
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
            ds.setURL("jdbc:h2:mem:outbox295;DB_CLOSE_DELAY=-1");
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
        public OrderService orderService(JdbcTemplate jdbc) {
            return new OrderService(jdbc);
        }
    }
}
~~~

### Run

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.OutboxDemo
~~~

Lines intentionally printed by the program, in expected order:

~~~text
after commit: orders=1 pending=1
rollback cause=force rollback
after rollback: orders=1 pending=1
broker delivered type=OrderPlaced aggregate=ORD-295
consumer applied aggregate=ORD-295
simulated crash before ack
broker delivered type=OrderPlaced aggregate=ORD-295
consumer duplicate skipped aggregate=ORD-295
final: pending=0 sent=1 applied=1
~~~

### Result Explanation

**Success:** Spring's AOP transaction proxy opens T1. `JdbcTemplate` writes to both `orders` and `outbox` on the same `DataSource`/transaction manager. When the service returns, T1 commits; both orders and pending counts are 1.

**Rollback:** T2 writes to both tables and throws `IllegalStateException`. The transaction interceptor rolls back T2; `ORD-ROLLBACK` has neither a business record nor an outbox record. Both counts after rollback remain unchanged.

**First send:** the relay reads the `PENDING` row and sends it to the broker stub; the consumer records the event ID. Because `acknowledge=false`, the relay does not update the status, simulating a crash after send before ack.

**Second send:** the row is still `PENDING`, so the relay resends the **exact same eventId**. The consumer detects the duplicate via `HashSet` and skips the side effect; the relay updates `SENT`. The consumer applied count stays 1.

### Limitations of the Example

- There is no Kafka, network ack, rebalance, offset, or durable broker.
- The consumer's `HashSet` is in-memory; real systems must use a **durable `processed_events` table** with a unique constraint/idempotency key.
- The relay does not lock and assumes a single worker; multiple replicas need row claiming/leasing.
- The SQL does not manage backoff, retries, retention, DLQ, schema versions, or migrations.
- Does not prove end-to-end exactly-once. It only illustrates the failure windows and necessary safeguards.
- The JSON payload is a fixed string for the demo. Real applications must use Jackson/a schema-compliant serializer rather than concatenating arbitrary input into JSON.

## 7. Production Polling Relay: Claiming, Retries, Leases

A polling publisher typically works in a loop:

~~~text
1. SELECT events ready to send
2. Claim using a short transaction/lock/lease
3. Send to broker, wait for appropriate delivery confirmation
4. Success -> mark SENT
5. Error -> attempts++, next_retry_at, last_error
6. Crash during PROCESSING -> lease expires, another worker retries
7. Controlled cleanup/archival after SENT
~~~

Never run multiple relays executing:

~~~java
// Counterexample with two workers running concurrently:
List<Event> events = findPending();
for (Event event : events) {
    broker.send(event);
    markSent(event);
}
~~~

Two workers can read the same `PENDING` row simultaneously and both send it before either marks it. This is one reason duplicates must still be tolerated.

### Safer Claiming

Techniques:

- `SELECT ... FOR UPDATE SKIP LOCKED` on databases that support it, inside a **short claim transaction**.
- Atomic `UPDATE status='PROCESSING' WHERE status='PENDING'`, checking affected row count.
- Leases `claimed_by`, `lease_until` to recover when a worker crashes.
- Optimistic locking using a version column.
- Partition routing to reduce contention.

**PostgreSQL-specific** example, not H2 demo SQL:

~~~sql
BEGIN;

SELECT event_id
FROM outbox_events
WHERE status = 'PENDING'
ORDER BY created_at, event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Claim the selected events as PROCESSING, recording lease owner/expiry
-- within the same short transaction.
COMMIT;
~~~

Do not keep a DB lock transaction open across a potentially long broker call. Claiming and acking are two separate transactions, so the crash gap still exists and consumer idempotency remains mandatory.

### Retry Policy

| Failure | Appropriate action |
|---|---|
| Network timeout, temporary broker outage | Exponential backoff with jitter and retry |
| Rate limiting/HTTP 429 | Honor throttling/`Retry-After` when present |
| Unserializable payload | Quarantine, DLQ, alert; do not retry infinitely |
| Auth/cert/permission | Fix configuration then retry in a controlled way |
| Message sent but ack unclear | May resend **the same eventId** |
| Permanent consumer business error | DLQ or manual resolution workflow |

**Only mark SENT after the right broker ack criterion is met.** Marking before send risks losing messages; marking after send risks duplicates. The outbox chooses **no loss** and requires consumers to deduplicate.

## 8. CDC / Debezium Outbox Event Router

**Polling** reads the outbox table periodically. The second approach is **transaction log tailing / CDC**: a connector like Debezium reads committed changes from the DB transaction log and forwards records to a broker. Debezium includes an **Outbox Event Router SMT** (single message transformation).

The default schema used by the Debezium Outbox Router documentation includes:

| Default field | Meaning |
|---|---|
| `id` | Event ID; placed into message header |
| `aggregatetype` | Routes to topic by aggregate type |
| `aggregateid` | Message key; useful for Kafka partition ordering |
| `type` | Event type |
| `payload` | Event content sent to consumers |

**Do not confuse the default CDC schema with the polling schema in section 4.** If using different column names, configure the corresponding mapping. Debezium Outbox Router assumes by default that the outbox table contains **INSERT event records**; updating row statuses like polling does may be treated as an invalid operation. Do not carry a `status=PENDING→SENT` design verbatim into the CDC Outbox SMT without checking the documentation and configuration.

### Comparison

| Criterion | Polling publisher | Debezium CDC |
|---|---|---|
| How events are detected | Queries pending rows | Reads DB commit log |
| Latency | Based on polling interval | Can be near real-time |
| Database impact | Queries/indexes/locking | Log capture and connector |
| Retry state | Managed by relay app | Connector offsets/broker/consumer |
| Infrastructure | Can be simpler | Requires CDC, connector, broker |
| Durability | Outbox row + retries | Commit log/connector + retries |
| Exactly-once business effect | Not automatically guaranteed | Not automatically guaranteed |

With CDC, you must manage connector snapshots, offsets, log retention, schema history, outbox cleanup, and DB permissions. CDC does not eliminate consumer deduplication requirements because deliveries can still repeat under system failure modes.

## 9. Durable Consumer Idempotency

A consumer must not rely solely on a `Set` like the demo. After a restart, the Set loses state, causing already-processed events to be applied again.

Track events per consumer:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Standard design for DB side effects:

~~~text
BEGIN T2
  INSERT processed_events(consumer_name, event_id, processed_at)
  - If duplicate key: recognize as already processed and do not reapply
  UPDATE downstream_projection(...), or write business side-effect table
COMMIT T2
ACK broker message
~~~

Key point: **inserting the processed marker and applying the business effect must share T2**. If you write processed in T2 and the business effect in T3, a crash in between causes redeliveries to be wrongly skipped.

PostgreSQL example:

~~~sql
INSERT INTO processed_events(consumer_name, event_id, processed_at)
VALUES ('billing', :eventId, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

The SQL above is **dialect-specific**. The consumer checks the inserted row count: 1 if new, 0 if already present; and executes in the same transaction as the business change. If the downstream side effect is email or an external API, it cannot be atomic with the local DB. You need an idempotency key at the target, a next-hop outbox, or a compensation mechanism.

### Broker Acknowledgment and Consumer Processing

Never ack the broker before the consumer's downstream changes have committed. Acking too early and crashing can lose work. Committing first and crashing before ack lets the broker redeliver; the inbox drops the duplicate.

**Producer's broker ack** differs from **consumer's ack** and differs from **business effect processed**. Dashboards must separate these three concepts.

## 10. Ordering: aggregateId, Versions, and Multiple Events

The outbox guarantees a record exists to relay; it does not automatically guarantee all consumers process events in final order when parallelism, retries, partitions, or multiple producers are involved.

~~~text
OrderPlaced(aggregate=ORD-295, version=1)
OrderPaid(aggregate=ORD-295, version=2)
OrderShipped(aggregate=ORD-295, version=3)
~~~

Measures:

1. Use `aggregateId` as the Kafka message key so events for the same aggregate usually land in the same partition **when mapping is consistent**.
2. Add `aggregateVersion` or a sequence assigned inside the aggregate's transaction.
3. Use optimistic locking to prevent concurrent writers from issuing duplicate versions.
4. Consumers persist `lastAppliedVersion` and handle stale/gap cases per contract.
5. Design the relay around the proper commit/sequence order; `created_at` does not prove absolute commit order.
6. With multiple types/streams for one aggregate, version increments may not be contiguous at every individual consumer.

Example rule:

~~~text
incoming.version <= lastAppliedVersion  -> stale/duplicate
incoming.version == lastAppliedVersion+1 -> apply for contiguous stream
incoming.version > lastAppliedVersion+1  -> gap, wait for replay/resync
~~~

This is not a rule enforced by Spring. If a consumer ignores certain event types or one aggregate version emits multiple events, design a different sequence contract. Timestamps and random UUIDs do not replace a clearly defined commit order.

## 11. Spring Modulith Event Publication Registry

**Spring Modulith** provides an **Event Publication Registry** for application events targeting transactional listeners. According to Spring Modulith documentation, within the business transaction the registry records publication entries for interested listeners; once a listener finishes successfully, the entry is marked completed. Incomplete publications can be managed and resubmitted according to the configuration/API of the corresponding version.

Distinguish the layers:

| Tool | What problem does it solve? |
|---|---|
| Spring Framework's `ApplicationEventPublisher` | In-process event publishing/dispatching |
| `@TransactionalEventListener` | Selecting phase when transaction commits/rolls back |
| Spring Modulith Event Publication Registry | Recording and recovering publications to transactional listeners |
| Outbox table + relay | Durably delivering integration events to brokers/APIs |
| Inbox + idempotency | Consumer deduplication and side-effect handling |

Spring Modulith's registry fits well when you need **reliable event listener execution across modules within the same application**. It does **not automatically** turn every event into a Kafka message or replace broker connectors and downstream inboxes.

For events going through a broker, you can integrate a listener forwarding to the broker with a dedicated design, or use an outbox/CDC directly. If combining both mechanisms, avoid unexpectedly emitting an event twice and define clear transaction boundaries.

Resubmission APIs and publication states differ across Spring Modulith versions; check the **exact version in use** rather than copying options verbatim from newer versions.

## 12. Transactions, Proxies, and Ways Atomicity Breaks

### Self-Invocation

~~~java
@Service
class CheckoutService {
    public void checkout() {
        this.writeOrderAndOutbox(); // Bypasses Spring proxy.
    }

    @Transactional
    public void writeOrderAndOutbox() {
        // Annotation may not start a transaction as expected.
    }
}
~~~

With Spring's default AOP proxy mode, `this.method()` bypasses the proxy. INSERTs risk auto-committing statement by statement. Fix by calling through an external bean proxy or `TransactionTemplate`, and actually test rollback.

### Two DataSources

~~~text
DataSource A: orders INSERT
DataSource B: outbox INSERT
~~~

If two datasources do not share a transaction coordinator, `@Transactional` on one method does not create atomicity between them. The outbox must live in the same guaranteed commit resource. For multi-database architectures, consider ownership redesign, sagas, event stores, or deliberate distributed transactions after evaluating trade-offs.

### Catching and Swallowing Errors

~~~java
@Transactional
public void place(String id) {
    orders.insert(id);
    try {
        outbox.insert(id);
    } catch (Exception ex) {
        log.warn("outbox failed", ex);
        // Wrong if the business transaction still commits.
    }
}
~~~

This is a counterexample. If the outbox INSERT is mandatory, exceptions must trigger rollback per rules or mark the transaction rollback-only. Never log-and-continue and accept a business row missing its event. Mind checked exceptions and `rollbackFor`: under common defaults, runtime exceptions trigger rollback while checked exceptions do not necessarily.

### @Async Does Not Carry the Source Transaction

Offloading the outbox INSERT to an `@Async` worker normally splits threads and transaction resources, breaking atomicity with T1. Tracing/MDC context propagation is not transaction propagation. Write the outbox **synchronously inside T1**, and only run the relay asynchronously after commit.

## 13. Reliability Testing: Fault Injection Is Required

Do not test only the happy path. An integration test suite should prove:

| Test | How to trigger the scenario | Assertion |
|---|---|---|
| Commit | Write business + outbox, commit T1 | Both rows exist |
| Rollback | Throw exception after both INSERTs | Neither row from failed T1 remains |
| Outbox INSERT failure | Violate constraint/DB error | Business INSERT also rolls back |
| Crash before relay | Leave PENDING then restart worker | Message is eventually sent |
| Crash after send before ack | Intentionally skip marking SENT then rerun | Same eventId is resent |
| Duplicate at consumer | Deliver E1 twice | Side effect applies only once |
| Concurrent workers | Two relays claim same rows | No out-of-policy double-claim; idempotency handles retries |
| Out-of-order | Deliver version 3 before version 2 | Projection does not revert to stale state |
| Broker timeout | Throw simulated error | Retry/backoff, does not mark SENT prematurely |
| Schema migration | v1 event still in outbox when deploying v2 | Relay/consumer can still deserialize |
| Cleanup | Purge SENT after retention | PENDING/processing rows needing retry are preserved |

A test method annotated with `@Transactional` in Spring TestContext normally **rolls back at the end**, so to verify real commits, do not accidentally fold the service transaction into an uncommitted test transaction. You can have a non-transactional test method call the service proxy, or use `TestTransaction.flagForCommit()` and `TestTransaction.end()` when a test-managed transaction is genuinely active.

**The `ApplicationEvents` test recorder only captures events published during the test**, not whether a broker sent them or an outbox row committed; verify the DB/relay and consumer outcomes separately.

## 14. Observability and Operations

Track the pipeline as distinct steps:

~~~text
Business commit
    -> Outbox PENDING
    -> Relay claim
    -> Broker ack
    -> Consumer received
    -> Consumer processed
    -> Downstream effect completed
~~~

Typically useful metrics:

- `outbox.pending.count` and `outbox.oldest.pending.age`: is the queue backing up?
- `outbox.relay.attempts`, `outbox.relay.errors`, `outbox.relay.backoff`: is the relay failing or throttling?
- `outbox.delivery.latency`: how long from commit to broker ack?
- `consumer.duplicates.count`: are retries spiking abnormally?
- `consumer.processing.errors` and `consumer.processing.latency`: is downstream succeeding?
- `outbox.dead_letter.count`: events needing manual intervention?
- `consumer.lag` by aggregate/topic when using a broker: any lag/ordering issues?

Alert on backlog age, retry failures, and SLOs, not merely total row counts. `SENT` at the producer does not prove downstream side effects succeeded.

**Cardinality:** `event.type`/`relay.name`/`outcome` are bounded tags; avoid turning `eventId`, `aggregateId`, email, or `userId` into high-cardinality metric labels. For tracing, store just enough correlation/causation metadata in accordance with security policies; traces do not replace durability.

## 15. Schema Evolution, Retention, and Security

Outboxes can survive across deployments or outages, so payloads must tolerate version skew.

- **Versioned contract:** event type, `schemaVersion`, and backward/forward compatibility rules.
- **Immutable payload:** properly serialized snapshot/delta, holding no references to JPA entities.
- **Safe deserialization:** do not trust broker messages as pre-authorized data; validate schema and origin.
- **Data minimization:** avoid tokens, passwords, card numbers, and unnecessary PII.
- **Tenant isolation:** if `aggregateId` is unique per tenant, message keys/lookups must include tenant context and enforce permissions.
- **Retention:** purge only `SENT` rows per SLA; never delete `PENDING` just because it is old.
- **Replay authorization:** replays can resend emails/side effects if a consumer lacks idempotency; audit replay operations.
- **Backup consistency:** business tables and outbox share the same backup/recovery scope to avoid restoring business DB without the outbox.
- **CDC retention:** coordinate outbox cleanup, transaction logs, and connector offsets so replay/recovery is not broken.
- **Payload encryption:** if sensitive data must be stored, control DB/broker permissions and decryption key lifecycles for older messages.

Define clearly when `eventId`, `aggregateVersion`, and `occurredAt` are generated; do **not** use timestamps for strict ordering when distributed systems need reliable sequence.

## 16. Common Mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Believing `publishEvent` retries after restart | In-memory events are not durable | Outbox record in the same business transaction |
| Sending message before DB commit | Consumer receives event for rolled-back work | Relay reads only committed rows |
| Using only `AFTER_COMMIT` | Crash gap still loses messages | Write outbox before commit |
| Writing outbox inside an AFTER_COMMIT listener | Outbox sits in a different transaction | Write inside business T1 |
| Writing outbox in another datasource | Not in the same local transaction | Use the same DB/transaction resource |
| Marking SENT before broker ack | Crash causes lost event | Ack first then mark; accept duplicates |
| Deduplicating by aggregateId | Wrongly drops later valid events | Use eventId per occurrence |
| Deduplicating with an in-memory Set in production | Restarts lose history | Durable inbox unique constraint |
| Multiple relays without claim/lock | Send the same row concurrently | Leases, atomic updates, SKIP LOCKED |
| Expecting outbox alone to give exactly-once | Crash between send/ack still resends | Idempotent consumers and side effects |
| Using created_at as guaranteed commit order | Insert time differs from commit time | Aggregate version/ordering contract |
| Applying polling UPDATE to insert-only CDC | Debezium SMT has a different contract | Design schema/SMT properly |
| Not testing old schemas | Pending events fail to read after deploy | Versioned serializers/consumers |
| Swallowing outbox INSERT exceptions | Business may commit missing its event | Roll back the unit of work |
| @Async writing outbox after T1 | Breaks atomicity | Write in T1; use async only for relay |
| Not monitoring pending age | Queue stalls unnoticed | Metrics/alerts and DLQ |
| Deleting pending rows for retention | Unsent events are lost | Clean up by status/SLA |
| Exposing secrets in payloads | DB/broker security exposure | Data minimization, ACLs, encryption |

## 17. Pre-Production Checklist

1. Do the business row and outbox row genuinely use **the same transaction**?
2. When the outbox INSERT fails, does the business transaction roll back?
3. Does each event have a distinct `eventId`, stable across retries?
4. Does the payload include `aggregateId`, type, `schemaVersion`, and required data?
5. Does the relay use polling or CDC; does the schema match the contract?
6. Does multi-worker execution have claiming/leasing/failover and handle crash gaps?
7. When the broker ack is unclear, does the system retry with the same `eventId`?
8. Does the consumer have a durable idempotency store/unique constraint?
9. Do the consumer's side effect and processed marker commit together in T2?
10. How is ordering by aggregate and version enforced?
11. Are retries, backoff, DLQ, visibility timeouts, and alerts in place?
12. Have crashes after send before ack, concurrency, and failure paths been tested?
13. Are retention, replay, schema migration, and security policies defined?
14. Does the business SLO measure **consumer completion**, not just producer `SENT`?
15. Do Spring Modulith's registry and an integration outbox overlap in responsibilities or emit duplicate events?

## 18. Review Questions

**1. Why is sending to Kafka directly inside `@Transactional` dangerous?** Because Kafka sends and JDBC commits do not form one local atomic transaction; a successful send followed by a DB rollback creates an orphan event.

**2. Is `@TransactionalEventListener(AFTER_COMMIT)` equivalent to an outbox?** No. It determines callback timing, not durable persistence of the event before commit.

**3. Does an outbox guarantee sending exactly once?** Usually no. The relay can resend after a crash, so consumers must be idempotent.

**4. Why can't eventId be replaced by orderId?** One order has many valid events; deduplicating by `orderId` would wrongly drop subsequent updates.

**5. Where should the outbox and business row live?** In the same local transaction/resource for atomic commit or rollback.

**6. How does polling differ from CDC?** Polling queries/claims outbox rows; CDC reads the transaction log and has its own schema/mapping/offsets.

**7. Does Debezium Outbox Router use the exact PENDING/SENT polling schema?** Not by default; the SMT expects INSERT event rows and uses its own mapping.

**8. Does Spring Modulith Event Publication Registry automatically send to Kafka?** Not automatically; the registry tracks publications to transactional listeners, while broker integration needs separate configuration/solutions.

**9. How should a consumer handle duplicates?** Persist processed `eventId` durably together with the business side effect in one transaction whenever possible; for external APIs, use idempotency keys or equivalent mechanisms.

**10. What is the core benefit of a transactional outbox?** If the business transaction commits, a durable event record exists to relay; if it rolls back, the event record rolls back too.

## 19. Conclusion and Official Documentation

The **Transactional Outbox Pattern** solves the dual-write problem by putting the **business update and a durable event record into the same DB transaction**. A relay delivers events externally after commit, retrying across network errors or process crashes. Because broker acks and outbox `SENT` updates cannot be atomic in standard setups, duplicates are a reality to plan for; consumers need idempotency alongside ordering, versioning, and event schema controls.

Spring Framework Application Events remains appropriate for in-JVM events; `@TransactionalEventListener` helps with phase timing but does not make events durable on its own. Spring Modulith's Event Publication Registry supports reliable publication across transactional listeners in modular designs; Debezium Outbox Event Router supports CDC publication to brokers with its own schema. Pick the right tool for the goal: **persisting events atomically with business commits**, **delivering to external systems**, or **processing internal resubmittable events**.

Reference documentation:

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html).
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- [Spring Framework — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- [Spring Modulith 1.4 — Working with Application Events](https://docs.spring.io/spring-modulith/reference/1.4/events.html).
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html).
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html).
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html).
