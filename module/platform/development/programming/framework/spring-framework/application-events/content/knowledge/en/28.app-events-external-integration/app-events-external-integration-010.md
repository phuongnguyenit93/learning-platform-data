# Do Not Use ApplicationEvent as a Durable Queue in Spring Framework

## 1. Lesson objectives

Spring Framework Application Events are an **internal notification mechanism within a single `ApplicationContext`**. They work well for decoupling components inside the same application: one service emits an event, and multiple listeners react without the publisher directly calling each listener.

However, **an `ApplicationEvent` is not a durable message queue**. In plain Spring Framework configuration, `ApplicationEventPublisher.publishEvent(...)` does not persist messages to a database or broker; nor does it provide durable processing acknowledgments, retries after process death, dead-letter queues, consumer offsets, or replayable history.

This is especially critical in the **External Integration** category: sending messages to external systems, calling payment gateways, sending transactional emails, updating inventory, syncing data to ERP/CRM, or emitting events to microservices. Those tasks usually demand **recovery after crashes**, not merely invoking a callback while the JVM stays alive.

By the end of this lesson, you will know how to:

1. Distinguish **internal event dispatch** from **durable message delivery**.
2. Explain why synchronous listeners, `@Async`, and `@TransactionalEventListener(AFTER_COMMIT)` all have durability limits.
3. Analyze the **failure windows** between database commit, event publication, broker ACK, and consumer side effects.
4. Design a **transactional outbox, relay, message broker, and idempotent inbox** for at-least-once delivery.
5. Choose among Kafka, RabbitMQ, a durable job table, and **Spring Modulith Event Publication Registry** when appropriate.
6. Run a Java 17+ example showing that a plain listener loses state when the context is recreated, whereas an outbox persisted in a database still retains records to process.
7. Test crashes, duplicates, redrives, ordering, observability, and security before deployment.

**Core message:** `publishEvent(...)` is an in-application notification/handoff operation, **not a guarantee that “the message is durably stored and will definitely be processed”**.

## 2. What do Spring Application Events actually do?

Core components:

| Component | Responsibility |
| --- | --- |
| `ApplicationEventPublisher` | API for emitting an event from application code |
| `ApplicationEventMulticaster` | Determines how events are dispatched to listeners |
| `SimpleApplicationEventMulticaster` | Default implementation; invokes listeners synchronously if no executor is configured |
| `@EventListener` | Registers a method to handle events on a Spring bean |
| `@Async @EventListener` | Schedules listener method via an executor if async support is enabled |
| `@TransactionalEventListener` | Binds callback execution to a phase of an existing transaction |
| Message broker | Separate infrastructure with logs/queues, consumers, ACK/offsets, and durable storage config |
| Transactional outbox | Message record persisted in the same DB transaction as business data |

Spring bean example:

~~~java
// Illustrative; requires OrderPlaced and a Spring-managed bean.
public void placeOrder(long orderId) {
    repository.saveOrder(orderId);
    publisher.publishEvent(new OrderPlaced(orderId));
}

@EventListener
public void notifyCustomer(OrderPlaced event) {
    mailClient.sendOrderConfirmation(event.orderId());
}
~~~

With the **default `SimpleApplicationEventMulticaster`**, synchronous listeners execute on the publisher’s thread. If the listener sends an email successfully and the method later throws an exception, the database may roll back while the external email cannot be “rolled back”. If the JVM stops at an unfortunate moment, there is no built-in Spring Framework record to automatically resend the email.

Diagram:

~~~text
OrderService / publisher thread
     |
     +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
                    |
                    +-- SimpleApplicationEventMulticaster
                           |
                           +-- @EventListener A
                           +-- @EventListener B
                           +-- ...
     |
     +-- caller continues (after synchronous listeners)
~~~

The event object can be a subclass of `ApplicationEvent` or a POJO/record. For POJOs, Spring can use `PayloadApplicationEvent` for dispatch. **None of these event types is persisted by default** merely by being published.

### 2.1. Synchronous does not mean durable

It is true that the default publisher **waits for synchronous listeners to finish**. That can let the caller detect certain errors immediately, yet it does not give you:

- **atomicity** with side effects outside the transaction, such as payment/email APIs;
- automatic retries across JVM restarts;
- consumer checkpoints/offsets;
- replayable message history;
- DLQs or redrives;
- delivery guarantees when the publisher or consumer process dies;
- decoupling across separate applications.

A synchronous call can be useful for validation/invariants within the same application, but it does not become a message queue on its own.

### 2.2. Async does not mean durable

~~~java
// Illustrative in a Spring bean; requires @EnableAsync.
@Async("notificationExecutor")
@EventListener
public void sendReceipt(OrderPlaced event) {
    mailClient.sendOrderConfirmation(event.orderId());
}
~~~

If `notificationExecutor` is a regular `ThreadPoolTaskExecutor`, tasks sit in an in-JVM thread pool/queue. When the process dies, queued or in-flight tasks can be lost. Callers are also not notified by default when an async listener fails.

Even if you configure `setWaitForTasksToCompleteOnShutdown(true)`, that is a **graceful** shutdown policy; it does not protect against process kills, power loss, forced container termination, or crashes before shutdown hooks run. Queues can also fill up and reject tasks.

### 2.3. Replacing the multicaster with an executor does not change its nature

~~~java
// Configuration snippet; requires an appropriate Executor.
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster multicaster(Executor eventExecutor) {
    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(eventExecutor);
    return m;
}
~~~

This can schedule many listeners asynchronously. Yet it remains **in-process dispatch**, creating no broker or durable log. Some listeners report `supportsAsyncExecution()==false`, including transaction-synchronized cases, and still must run on the publisher thread to preserve semantics. Never force every listener to run async and assume you now have reliability.

## 3. Analyzing message loss intervals (failure windows)

Consider placing an order and notifying another service. There are two naive implementations, both with risk windows.

### 3.1. Commit database first, then publish event

~~~text
1. BEGIN TRANSACTION
2. INSERT orders
3. COMMIT                [order exists]
4. publishEvent(...)
5. listener sends message externally
~~~

If the JVM **crashes between steps 3 and 4**, the order is saved yet nobody knows a notification must be sent. There is no durable record for replay.

Even after step 4, an async listener may not have run yet. Crashing there loses the queued task.

### 3.2. Publish event before commit

~~~text
1. BEGIN TRANSACTION
2. INSERT orders
3. publishEvent(...)
4. listener calls partner API
5. COMMIT or ROLLBACK
~~~

If the partner API received the message and the transaction **rolls back** at step 5, the outside world has a side effect for a nonexistent order. A synchronous callback cannot undo an external API call.

If the listener runs async, it may query the database before the transaction commits and fail to see the data. Calling `publishEvent(...)` inside `@Transactional` does not make the worker join the old transaction.

### 3.3. Using AFTER_COMMIT

~~~java
// Illustrative Spring bean.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publishIntegrationEvent(OrderPlaced event) {
    externalPublisher.send(event);
}
~~~

This avoids emitting a message when the source transaction rolls back, yet a **crash gap remains between `COMMIT` and callback/send completion**. `AFTER_COMMIT` does not mean the message is persisted for automatic retry after restart.

By default, `@TransactionalEventListener` ignores events published outside a transaction (`fallbackExecution=false`). Other phases include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`; they govern **callback timing**, not substitute for a durable queue.

### 3.4. Failure windows table

| Crash/failure timing | With ApplicationEvent only | With durable outbox |
| --- | --- | --- |
| Before DB commit | Transaction can roll back | Order and outbox roll back together |
| After commit, before publish | Notification can be lost permanently | Outbox record still exists |
| After event dispatched to executor, before worker runs | In-memory task can be lost | Relay can still read unsent record |
| Broker receives message, ACK to relay is lost | No standard Spring Context checkpoint | Relay can resend; idempotency required |
| Consumer succeeds then crashes before ACK | No consumer offset | Message can be redelivered; consumer deduplicates |
| Downstream temporarily unavailable | Sync error/async callback fails per code | Retry policy and DLQ per broker/consumer |
| Consumer receives unsupported payload | No built-in DLT | Can route to DLQ for inspection and redrive |

The key is to ask not just “did we call publish?”, but **“where is the intent to emit the message persisted, and who recovers it after a crash?”**.

## 4. Defining guarantee levels accurately (delivery semantics)

Three commonly confused concepts:

**At-most-once:** processed at most one time. Messages can be lost if a failure occurs. An in-memory event with no retry/recovery mechanism generally cannot meet eventual-processing requirements.

**At-least-once:** the system can redeliver a message until successful processing is confirmed. In exchange, **duplicates** can occur. This is the practical standard model when pairing an outbox + broker + idempotent consumer.

**Exactly-once:** you must specify *exactly once within what scope*. Some brokers/stream processors offer exactly-once within specific transaction/log boundaries, but that does not guarantee once-only execution across every database, HTTP API, email, and payment gateway end-to-end.

For example, the broker delivers a message, the consumer calls the payment API successfully, and then crashes before recording the ACK. When the message is redelivered, the payment API may be called again. To prevent double charging, the consumer needs a stable **idempotency key**, handling of ambiguous outcomes, and/or reconciliation.

Never promise “end-to-end exactly-once” merely from adding `@Transactional`, Kafka transactions, or a local unique constraint.

## 5. Recommended architecture for external integration

A common model:

~~~text
OrderService
   |
   +-- BEGIN DB TRANSACTION
   |       +-- INSERT/UPDATE orders
   |       +-- INSERT outbox_events (eventId, payload, status=NEW)
   |   COMMIT
   |
   +-- Relay / CDC
           |
           +-- broker (Kafka / RabbitMQ / messaging service)
                   |
                   +-- consumer A
                   |       +-- inbox/processed_events
                   |       +-- DB/API side effect
                   |       +-- timely ACK
                   |
                   +-- consumer B
                           +-- idempotent processing
                           +-- retry / DLQ
~~~

Components:

1. **Producer transaction** writes business data and outbox records **in the same database transaction**.
2. **Outbox relay** reads unsent records, publishes to the broker, handles ACKs/failures, and updates delivery status.
3. **Broker** holds messages per durability/retention/replication settings; decouples producer from consumer.
4. **Consumer** processes, stores processed markers/inbox rows, and acknowledges messages at the right boundary.
5. **Retry + dead-letter** handle transient/permanent errors; monitored, bounded, loop-free.
6. **Reconciliation/compensation** repairs business state if final side effects cannot complete.

This is not a single Spring Framework annotation; it requires storage schemas, jobs, transactions, broker configuration, monitoring, and failure-window testing.

## 6. Transactional outbox: atomic intent

Suppose an order transitions to `CREATED`. Instead of only publishing an in-memory event, **write an outbox record at the same time**:

~~~sql
-- Illustrative SQL; exact data types depend on the RDBMS.
CREATE TABLE orders (
    order_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(80) PRIMARY KEY,
    aggregate_id VARCHAR(80) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(120) NOT NULL,
    schema_version INT NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    next_attempt_at TIMESTAMP,
    leased_until TIMESTAMP
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Benefit: if the transaction **rolls back**, neither order nor outbox exists; if it **commits**, both exist. There is no longer a gap where “the order committed, but the intent to send the message wasn’t saved”.

### Notes on atomicity

- Do not use two separate transactions for `orders` and `outbox`; that still leaves a dual-write gap.
- Do not call the broker before commit and expect the broker to roll back with the DB.
- Do not write the outbox from `@TransactionalEventListener(AFTER_COMMIT)` in a new transaction and call it atomic with the original order: if the process dies after order commit and before the callback, the outbox record is still lost.
- If the outbox must be written in the current transaction, write directly via a repository or a mechanism guaranteed to run before commit with proper transaction semantics; test rollbacks too.
- Avoid payloads containing live JPA entities, `HttpServletRequest`, security tokens, or schemaless objects; serialize integration events into versioned DTOs.

### Event envelope

~~~java
// Java snippet: data must be explicitly serialized and persisted.
public record IntegrationEvent(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        String correlationId,
        String causationId,
        String occurredAt,
        String payloadJson
) {}
~~~

**`eventId`** stays stable across retries/redeliveries; **`aggregateId`** serves as the message key/partitioning key when per-aggregate ordering is needed; **`schemaVersion`** lets consumers evolve gradually; correlation/causation support tracing.

Avoid full entity snapshots when only a few business facts are needed. An integration event is a **contract between systems**, requiring versioning, data minimization, and backward-compatibility policies.

## 7. Outbox relay: polling or CDC

Two common implementation approaches.

### 7.1. Polling relay

A worker periodically selects a batch of outbox rows in `NEW` state or due for retry. With multiple instances, safe **claiming/leasing** is needed to avoid excessive concurrent duplicates.

Basic flow:

~~~text
poll NEW / retryable records
    |
    +-- claim batch safely (lease + owner + deadline)
    +-- publish to broker with eventId/key
    +-- wait for broker acknowledgment per policy
    +-- mark SENT or PUBLISHED
    |
    +-- error -> increment attempts, backoff, keep record for retry
~~~

A SQL pattern like `SELECT ... FOR UPDATE SKIP LOCKED` can help on supporting databases, but never copy the statement verbatim to every DB without checking semantics. A relay crash between broker ACK and marking `SENT` will cause the event to be **resent**. Thus at-least-once + consumer idempotency remain necessary.

**Never mark `SENT` before confirming the broker accepted it per contract.** If the process crashes after marking `SENT` yet before actually publishing, the record can be irrecoverably lost.

Bound batch sizes, timeouts, queues, backoff, and retention. Otherwise, the outbox can grow unbounded when the broker is unavailable.

### 7.2. CDC / change data capture

A tool like Debezium can read the database change log and emit outbox records to a broker. This avoids continuous polling and reduces custom relay code, but still requires:

- DB transactions for business data and the outbox.
- Connector deployment, checkpoints/offsets, and schema mapping.
- Monitoring replication slots/log retention and consumer lag.
- Idempotent consumers on duplicates/restarts.
- Plans for schema/partition-key changes and replays.

CDC does not “automatically turn `@EventListener` into a Kafka event”. Data tracked by CDC must be persisted in an appropriate database structure.

## 8. Idempotent consumers and inboxes

Even when the outbox guarantees not losing **publication intent**, the broker/relay can deliver duplicates. Consumers must tolerate them.

~~~text
receive(eventId=evt-101)
    |
    +-- BEGIN consumer DB transaction
    |       +-- INSERT processed_events(consumer, evt-101)
    |       +-- UPDATE local business state
    |   COMMIT
    |
    +-- ACK message
~~~

A unique constraint on `(consumer_name, event_id)` detects duplicates. Never `SELECT` to check unprocessed and run side effects before `INSERT`ing the marker: two workers can both see it as unprocessed and execute together. You need transactions, unique constraints, and explicit design for external side effects.

For an external payment API outside the DB transaction, recording “processed” **before** calling can lose work on crash; recording **after** calling can repeat calls on ambiguous outcomes. You need stable external idempotency keys and/or outcome queries/reconciliation.

### Idempotency does not mean ignoring every event for the same aggregate

Deduplication keys should be based on **event ID and consumer**, not `orderId` alone. A single order legitimately has multiple distinct events (`OrderCreated`, `OrderPaid`, `OrderShipped`). Deduplicating solely by `orderId` causes the consumer to wrongly drop valid steps.

If a consumer’s processing depends on order, you need aggregate versions, optimistic locks, or partitioning by aggregate key; a unique `eventId` only prevents duplicates—**it does not guarantee ordering**.

## 9. Java 17+ demo: in-memory events vs. durable outbox across context recreation

The following example intentionally omits Kafka/RabbitMQ to focus on the lesson: **internal events are not persisted by Spring**, whereas an outbox record written to a **file-backed H2 database** survives closing and recreating the `ApplicationContext`.

Environment:

- Java 17+, Maven.
- Spring Framework **6.2.12** (`spring-context`, `spring-jdbc`).
- H2 **2.3.232**, in **file-backed** mode (not `jdbc:h2:mem`).
- `TransactionTemplate` to write **orders + outbox** in one local DB transaction.
- Plain `@EventListener` only increments an in-memory counter.
- Mock relay/consumer reads the outbox after recreating the context and handles duplicates via a unique key.

**Transparent limitations:** the demo recreates the Spring `ApplicationContext` **within the same JVM** to observe lifecycle; it does not simulate power loss or test fsync of a production system. The mock consumer only writes a processed marker in the same H2 database, without sending to a real broker/API. Production requires proper relays, ACKs, retention, schemas, monitoring, and side-effect transactions.

### 9.1. Directory structure

~~~text
application-event-not-a-queue/
├── pom.xml
└── src/main/java/demo/NotAQueueDemo.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>application-event-not-a-queue</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. src/main/java/demo/NotAQueueDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class NotAQueueDemo {

    public record OrderCreated(String eventId, String orderId) {}
    public record OutboxRow(String eventId, String orderId) {}

    public static final class LocalListener {
        private final AtomicInteger received = new AtomicInteger();

        @EventListener
        public void on(OrderCreated event) {
            received.incrementAndGet();
        }

        public int count() {
            return received.get();
        }
    }

    public static final class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.publisher = publisher;
        }

        public void place(String orderId, String eventId) {
            // Order + outbox: one local transaction, commit or roll back together.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders (order_id, status) VALUES (?, ?)",
                    orderId, "CREATED");
                jdbc.update(
                    "INSERT INTO outbox_events "
                        + "(event_id, order_id, delivered) VALUES (?, ?, FALSE)",
                    eventId, orderId);
            });

            // In-process notification only; NOT a durable handoff.
            // If a crash occurs right before this line, the outbox remains for relay.
            publisher.publishEvent(new OrderCreated(eventId, orderId));
        }
    }

    public static final class OutboxRelay {
        private final JdbcTemplate jdbc;

        public OutboxRelay(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public int pending() {
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox_events WHERE delivered = FALSE",
                    Integer.class);
        }

        public OutboxRow firstPending() {
            List<OutboxRow> rows = jdbc.query(
                "SELECT event_id, order_id FROM outbox_events "
                    + "WHERE delivered = FALSE ORDER BY event_id",
                (rs, i) -> new OutboxRow(
                    rs.getString("event_id"),
                    rs.getString("order_id")));

            if (rows.size() != 1) {
                throw new IllegalStateException(
                    "Expected one pending outbox record");
            }
            return rows.get(0);
        }

        public void markDelivered(String eventId) {
            int changed = jdbc.update(
                "UPDATE outbox_events SET delivered = TRUE WHERE event_id = ?",
                eventId);
            if (changed != 1) {
                throw new IllegalStateException("Outbox update failed");
            }
        }
    }

    public static final class MockConsumer {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;

        public MockConsumer(JdbcTemplate jdbc, TransactionTemplate tx) {
            this.jdbc = jdbc;
            this.tx = tx;
        }

        // Simulates a local consumer DB transaction only.
        public boolean processOnce(OutboxRow event) {
            try {
                return Boolean.TRUE.equals(tx.execute(status -> {
                    jdbc.update(
                        "INSERT INTO processed_events (event_id, order_id) "
                            + "VALUES (?, ?)",
                        event.eventId(), event.orderId());
                    return true;
                }));
            } catch (DuplicateKeyException duplicate) {
                return false;
            }
        }

        public int processedRows() {
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM processed_events",
                    Integer.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource dataSource =
                    new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(
                "jdbc:h2:file:./target/events-outbox-db;"
                    + "DB_CLOSE_ON_EXIT=FALSE");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public LocalListener localListener() {
            return new LocalListener();
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, tx, publisher);
        }

        @Bean
        public OutboxRelay outboxRelay(JdbcTemplate jdbc) {
            return new OutboxRelay(jdbc);
        }

        @Bean
        public MockConsumer mockConsumer(
                JdbcTemplate jdbc,
                TransactionTemplate tx) {
            return new MockConsumer(jdbc, tx);
        }
    }

    private static void resetDemoTables(JdbcTemplate jdbc) {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS orders ("
                + "order_id VARCHAR(80) PRIMARY KEY, "
                + "status VARCHAR(30) NOT NULL)");
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS outbox_events ("
                + "event_id VARCHAR(80) PRIMARY KEY, "
                + "order_id VARCHAR(80) NOT NULL, "
                + "delivered BOOLEAN NOT NULL)");
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS processed_events ("
                + "event_id VARCHAR(80) PRIMARY KEY, "
                + "order_id VARCHAR(80) NOT NULL)");

        // For deterministic demo only. Never clear production tables!
        jdbc.update("DELETE FROM processed_events");
        jdbc.update("DELETE FROM outbox_events");
        jdbc.update("DELETE FROM orders");
    }

    public static void main(String[] args) {
        // Phase 1: save order + outbox, dispatch plain in-process event.
        try (var first =
                new AnnotationConfigApplicationContext(Config.class)) {
            resetDemoTables(first.getBean(JdbcTemplate.class));

            first.getBean(OrderService.class).place("order-101", "evt-101");

            System.out.println(
                "memory-listener-before-close="
                    + first.getBean(LocalListener.class).count());
            System.out.println(
                "outbox-before-close="
                    + first.getBean(OutboxRelay.class).pending());
        }

        // Phase 2: different Spring ApplicationContext, same H2 file database.
        try (var second =
                new AnnotationConfigApplicationContext(Config.class)) {
            LocalListener listener = second.getBean(LocalListener.class);
            OutboxRelay relay = second.getBean(OutboxRelay.class);
            MockConsumer consumer = second.getBean(MockConsumer.class);

            System.out.println(
                "memory-listener-after-reopen=" + listener.count());
            System.out.println(
                "outbox-after-reopen=" + relay.pending());

            OutboxRow record = relay.firstPending();

            boolean firstDelivery = consumer.processOnce(record);
            boolean secondDelivery = consumer.processOnce(record);

            // Mark only after mock consumer confirms.
            relay.markDelivered(record.eventId());

            System.out.println("mock-consumer-first=" + firstDelivery);
            System.out.println(
                "mock-consumer-duplicate-skipped=" + !secondDelivery);
            System.out.println(
                "outbox-after-mock-relay=" + relay.pending());
            System.out.println(
                "processed-event-rows=" + consumer.processedRows());
        }
    }
}
~~~

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NotAQueueDemo
~~~

Eight lines printed by **the program itself** (Maven/Spring logs, if any, are separate):

~~~text
memory-listener-before-close=1
outbox-before-close=1
memory-listener-after-reopen=0
outbox-after-reopen=1
mock-consumer-first=true
mock-consumer-duplicate-skipped=true
outbox-after-mock-relay=0
processed-event-rows=1
~~~

### 9.4. Why does this output make sense?

1. `place(...)` calls `TransactionTemplate.executeWithoutResult(...)`, writing the `orders` and `outbox` rows in the **same transaction**, then commits.
2. `publisher.publishEvent(new OrderCreated(...))` calls the default synchronous listener in the first context. `LocalListener.received` increments to 1.
3. When the first context closes, the `LocalListener` bean and its counter are not persisted by Spring.
4. The second context instantiates a **fresh listener bean**, whose counter is 0. Spring **does not automatically replay** `OrderCreated` to the new context.
5. H2 runs in **file-backed** mode, so the committed outbox record persists; `pending=1` in the second context.
6. The mock consumer processes `eventId` `evt-101` the first time: `INSERT processed_events` succeeds.
7. The same event is processed a second time: the `event_id` primary key prevents duplication, `DuplicateKeyException` is caught, and the result is `false`.
8. After the mock consumer confirms the first run, the relay marks `delivered=true`; `pending=0` and `processed-event-rows=1`.

**Important:** this demo proves only the difference between **in-memory state tied to a context’s lifecycle** and **data records committed to a file-backed H2 database**. It does not prove a message broker received an event. The mock consumer shares the same DB, so there is no network boundary or two-service crash scenario. Production must clearly separate ACKs, transactions, and idempotency.

### 9.5. Fault-tolerance boundaries of the demo

- When re-running `main`, `resetDemoTables` **intentionally deletes demo data** so stdout stays reproducible. That is a test fixture, not production outbox behavior.
- The H2 file is created under `target/` via `jdbc:h2:file:./target/events-outbox-db`. Maven creates `target` during build; the program needs write permissions in the project directory.
- Closing/reopening a context **is not the same as abruptly killing a JVM**; real crash testing requires running two processes, killing at predetermined points, and inspecting DB and relay state.
- `markDelivered` in the demo runs after the mock consumer. When sending to a real broker, the relay must wait for the **broker ACK per policy** rather than waiting for end-to-end consumer completion; the consumer processes and ACKs independently.
- The consumer’s unique transaction constraint only blocks duplicates in the demo database. To avoid duplicate side effects on external APIs, you need external idempotency keys and handling for ambiguous outcomes.

## 10. What do Spring Kafka and RabbitMQ solve?

### Spring for Apache Kafka

Kafka maintains logs by topic/partition with cluster-configured retention and replication. Spring Kafka provides `KafkaTemplate`, `@KafkaListener`, container error handlers, retries/backoff, and dead-letter publishing. Conceptual example (snippet, not part of the section 9 Maven demo):

~~~java
// Requires spring-kafka and a configured KafkaTemplate.
@Bean
DefaultErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    // 1 initial try + 2 retries = at most 3 attempts.
    return new DefaultErrorHandler(
            recoverer, new FixedBackOff(1_000L, 2L));
}
~~~

Attach the handler to the actual listener container factory, verify offset commits/ACKs, and confirm DLT publishing. `DeadLetterPublishingRecoverer` has default destination rules depending on configuration/version (usually `-dlt` topic suffix); the DLT must be created with matching partitions.

**Kafka does not automatically turn a database write and a broker publish into one atomic local transaction** just because you added `@Transactional`. When orders live in a database separate from Kafka, an outbox or equivalent dual-write consistency mechanism is still required.

### Spring AMQP / RabbitMQ

RabbitMQ provides durable queues, persistent messages, publisher confirms, consumer acknowledgments, retry topologies, and dead-letter exchanges. Those features must **be explicitly configured**; they do not turn on automatically just by using Spring AMQP.

Questions to answer:

- Is the queue durable, and are messages published with appropriate delivery modes/confirms?
- Are ACKs sent **after** the consumer completes its side effects?
- When a consumer crashes before ACK, how are messages redelivered?
- When queues fill up or the broker is unavailable, what does the producer do?
- Are DLX/DLQ, bounded retries, TTL/retention, and a replay policy in place?
- Are replication/availability aligned with required SLAs?

A broker helps store/deliver messages, yet you still need idempotent consumers, timeouts, monitoring, and often a transactional outbox at the producer.

## 11. Spring Modulith Event Publication Registry: an intentional exception

An important caveat so you do not over-generalize the lesson: **Spring Modulith** is an extension project providing an **Event Publication Registry**, which can record event publications for transactional listeners in transaction-capable storage and mark them complete once processed. It also includes mechanisms to query/resubmit incomplete or failed publications depending on version/configuration.

This is **not the default behavior of Spring Framework’s `ApplicationEventPublisher`**. To get it, the application must add Spring Modulith dependencies, pick an appropriate repository backend (JDBC/JPA/MongoDB, etc.), configure schemas/transactions, and set resubmission policies.

Proper mental model:

- **Plain Spring Framework:** `ApplicationEventPublisher` + `@EventListener` alone never creates a durable queue.
- **Configured Spring Modulith Registry:** provides a persistent publication log for listeners supported by the registry; retries/resubmission depend on configuration and version.
- **External broker integration:** still needs externalization/publishing adapters, broker semantics, payload mapping, and consumer handling; the registry does not turn every local event into a distributed contract for all consumers.
- **Cross-service delivery:** still requires checking broker state, ACKs, and idempotency outside the application.

If the system is a modular monolith needing stronger reliability across modules inside the same application, Spring Modulith is worth considering. If the system must deliver messages to multiple independent services, thoroughly evaluate externalization, brokers, and outboxes before choosing tools.

## 12. Retries and dead-lettering must have boundaries

A true durable queue typically needs:

- Bounded attempts, exponential backoff, and jitter;
- per-attempt timeouts and a global deadline;
- distinction between transient, permanent, and ambiguous errors;
- load-shedding/backpressure policies when overloaded;
- a DLQ/DLT containing the original event, consumer, error code, and attempt count;
- a redrive runbook with approval and rate limits;
- retention, archiving, and sensitive-data controls;
- metrics for queue age / oldest outstanding item;
- compensation/sagas when failures cause business consequences.

**A DLQ does not perform compensation automatically.** A failed email does not mean an order needs a refund. Conversely, a payment failure may require an inventory compensation workflow before anyone handles the DLQ.

If a message is redriven after an order is already `CANCELLED`, the consumer must check state/version so it does not accidentally replay stale business actions. Retries keep the original `eventId`; if issuing a new command, give it its own ID and proper causation link.

## 13. Measuring reliability and backlog status

Useful metrics:

| Suggested metric | Purpose |
| --- | --- |
| `outbox.pending` | Number of unsent records |
| `outbox.oldest_age` | Age of the oldest unsent record |
| `relay.publish.duration` | Latency from relay to broker ACK |
| `relay.failures` | Count of failed publishes |
| `broker.consumer.lag` | Consumption lag per broker |
| `consumer.processing.errors` | Processing errors by consumer/event type |
| `consumer.duplicate.skipped` | Duplicates safely suppressed |
| `dlq.depth` / `dlq.oldest_age` | Messages needing investigation/redrive |
| `business.completion.latency` | Time from event emission to business task completion |

These are **illustrative metric names**, not metrics automatically exported by Spring Framework. Put detailed IDs in structured logs/traces; avoid using `eventId`/`orderId` as high-cardinality metric tags.

Do not alert solely on total pending count: an outbox with 5 messages whose oldest record is 2 days old may be far more alarming than 500 messages just created and draining normally.

### Observability does not replace replay

Correlation IDs and traces help debug incidents, yet a clean trace is not a durable log. If a job vanishes after a process crash with no outbox/broker record, logging/tracing is rarely enough to reconstruct exact payloads and state to resend.

## 14. Crash and duplicate testing checklist

### Producer

1. `orders` + `outbox` transaction commits: both rows exist.
2. Business transaction rolls back: both rows disappear.
3. Process dies **after commit but before in-process publish**: outbox still exists for the relay.
4. Relay crashes before broker ACK: `SENT` is not falsely marked.
5. Relay crashes after broker ACK but before marking `SENT`: message can be resent; consumer must be idempotent.
6. Broker unavailable for an extended period: pending outbox grows without being dropped; alerts and retry bounds exist.
7. Multiple relay instances: claiming/leasing prevents publish storms; test lease expiration.

### Consumer

1. Duplicate with same `eventId`: business side effect does not double.
2. One aggregate with multiple distinct `eventId`s: not falsely deduplicated by `orderId`.
3. Consumer crashes after DB commit but before message ACK: redelivery does not re-run the local transaction side effect.
4. External API timeout with ambiguous outcome: query status / retain idempotency key.
5. Old/new schemas: deserialize/transform cleanly and route failures to DLQ.
6. Out-of-order messages: aggregate version/state guards handle them cleanly.
7. DLQ redrive after completed compensation: do not accidentally re-charge a cancelled order.

### Spring-specific

1. Synchronous `@EventListener`: errors can propagate back to the publisher and callbacks block the publisher thread.
2. `@Async @EventListener`: in-memory tasks are lost on process crash; do not confuse graceful shutdown with abrupt kills.
3. `@TransactionalEventListener(AFTER_COMMIT)`: callbacks do not run on rollback, yet a post-commit crash gap remains.
4. Spring Modulith registry: test durability/resubmission only after genuinely installing and configuring storage/registry.
5. Broker integration: run tests against real Kafka/RabbitMQ or Testcontainers, verifying ACKs, retries, DLT/DLX, retention, and real redrives rather than relying on in-memory mocks.

**Important:** in tests, use `CountDownLatch`/Futures with timeouts to await async completion; never use a fixed `Thread.sleep` to claim processing finished.

## 15. Common mistakes

| Misconception | Risk | Right approach |
| --- | --- | --- |
| “`@EventListener` is already a message queue” | No durable storage | Use outbox/broker when needed |
| “`publishEvent` returning = downstream finished” | Async callbacks/workers may not have run | Separate dispatch from business completion |
| “Adding `@Async` prevents losing events” | In-memory executor queues lose tasks on crash | Durable queue/outbox |
| “`AFTER_COMMIT` guarantees message sending” | Post-commit crash gap still exists | Atomic outbox intent |
| “Saving order then sending to Kafka in the next method is atomic” | Dual-write inconsistency | Same-DB transaction outbox |
| “Broker send succeeded means consumer processed once” | Redeliveries/duplicates | Idempotent consumer/inbox |
| “Kafka exactly-once covers every external API” | Double charges/emails | Clear EOS scope and external idempotency |
| “Outbox relay can mark `SENT` before publishing” | Crash loses messages | Wait for broker ACK, handle duplicates |
| “One global unique `eventId` across all consumers” | Wrongly blocks other consumers | Key by `(consumer, eventId)` |
| “Outbox never needs cleanup” | Table grows unbounded | Retention/cleanup/archival |
| “Using in-memory H2 tests persistence” | Data vanishes when context/JVM stops | File-backed H2 or real DB |
| “Having Spring Modulith means all local events externalize automatically” | Misconfiguration, missing broker | Understand registry/externalization scope |
| “DLQ means the event was fixed” | Backlog silently piles up | Owner, runbook, alerts, redrive |
| “Retries generate a new `eventId` each time” | Deduplication breaks | Keep original event ID |
| “Every event must go to a broker” | Overengineering, higher latency/coupling | Keep local invariants inside services/txs |

## 16. Choosing an option by requirement

| Actual requirement | Typically suitable solution |
| --- | --- |
| Fast reaction inside the same `ApplicationContext`, no replay needed | Synchronous `@EventListener` |
| Auxiliary task acceptable to lose on process death, non-critical | `@Async @EventListener` with managed executor |
| Side effect should run only after commit, durable replay not required | `@TransactionalEventListener(AFTER_COMMIT)` |
| Notification must survive restarts within a modular monolith | Durable publication/outbox; consider Spring Modulith Registry |
| Integration event for multiple services requiring retries/replay | Transactional outbox + Kafka/RabbitMQ + idempotent consumers |
| Internal job must resume after crash, no event fan-out needed | Durable job table + worker with leases/attempts |
| Multi-step business workflow needing compensation on failure | Saga/process manager + durable messages + compensation |
| Event sourcing / full history audit | Dedicated event store, separate aggregate/version/replay design |

Do not choose solutions based on buzzwords like “async” or “event-driven”. First write down explicitly: **is message loss acceptable**, **is crash recovery required**, **who ACKs**, **how are duplicates handled**, and **when is business success confirmed**.

## 17. Practical implementation checklist

1. Are publisher and consumer in the same JVM or separate services/processes?
2. If the JVM dies right after DB commit, where does the event intent live?
3. Are business DB and outbox **in the same transaction**?
4. Are event ID, aggregate ID, schema version, and correlation ID recorded?
5. Does the relay use polling or CDC? How are claims/leases/offsets managed?
6. When broker publishing fails, does the outbox retain the message for retries?
7. If the broker accepts but the ACK to the relay is lost, how are duplicates handled?
8. Does the consumer ACK only after its local transaction has committed?
9. Do external APIs have idempotency keys/reconciliation?
10. Do retries/DLQ/redrives have bounds and runbooks?
11. Are there metrics for oldest pending, consumer lag, duplicates, and business completion?
12. Have process crashes, rollbacks, duplicates, out-of-order arrivals, and schema upgrades been tested?

**Conclusion:** Spring Application Events are well suited for **internal decoupling**, yet `ApplicationEventPublisher` is not a durable queue. Synchronous listeners do not make messages survive crashes; `@Async` only moves work to another thread; `@TransactionalEventListener` controls callback timing rather than eliminating the crash gap. When external integration requires reliability, **persist intent in the same transaction**, use a **relay/broker**, support **at-least-once delivery and idempotent consumers**, and operate real retries, DLQs, redrives, and metrics. Spring Modulith can add persistent event publication for suitable use cases, though it requires dedicated configuration.

## Official documentation and further reading

- Spring Framework — ApplicationContext Events and default multicaster: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — ApplicationEventPublisher Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework — Async execution: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Modulith — Working with Application Events / Event Publication Registry: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Kafka — Handling Exceptions, DefaultErrorHandler and DeadLetterPublishingRecoverer: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring AMQP — Messaging and listener containers: https://docs.spring.io/spring-amqp/reference/
