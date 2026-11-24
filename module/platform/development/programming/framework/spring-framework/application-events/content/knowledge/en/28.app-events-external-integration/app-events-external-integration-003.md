# Ensuring External Publishing After Commit in Spring Framework Application Events

## 1. The problem: data is committed, yet the external system never receives the event

Suppose an order processing service must perform two actions together:

1. Write the order status to the database.
2. Send an `OrderCommitted` event to Kafka, RabbitMQ, a webhook, or an external service for further processing.

If the event is sent **before the transaction commits**, the receiver may observe the event and act on it while the source transaction later rolls back. If it is sent only **after commit**, the database already holds the right result, but the process can crash, the network can drop, or the broker can reject the message before sending finishes. This is the **dual write** problem: the database and the broker are two systems with different commit boundaries.

```text
BEGIN TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
    broker.send(OrderCommitted)   <-- broker receives it
ROLLBACK                          <-- order was not committed!

Or:

BEGIN TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
COMMIT                            <-- order is persisted
process crash / broker timeout    <-- event was never sent!
```

Two symmetric risks:

- **Ghost event:** an event appears externally even though the business change rolled back.
- **Lost event:** a business change committed, yet the notification event is never delivered externally.

Spring Application Events provides `@TransactionalEventListener(phase = AFTER_COMMIT)` so that **the callback does not run before a successful commit**. However, this callback still lives **in the process’s memory**; if the process dies after commit and before sending, the callback may never execute. Therefore, you must distinguish “publish only after commit” from “guarantee eventual publish after commit”.

### Learning objectives

After this lesson, you can:

- Distinguish `AFTER_COMMIT`, `AFTER_ROLLBACK`, `BEFORE_COMMIT`, and `AFTER_COMPLETION`.
- Understand why a synchronous `@EventListener` calling a broker inside a transaction can create ghost events.
- Use `@TransactionalEventListener(AFTER_COMMIT)` for **best-effort** work, and know its crash window.
- Understand why writing to the database in a post-commit callback requires a new transaction, such as `REQUIRES_NEW`.
- Design a **transactional outbox**: event records are persisted **in the same business transaction**, and an independent relay sends only committed records.
- Build retries, broker confirmations, sent markers, idempotency, and multi-worker claiming mechanisms.
- Test rollbacks, transient broker failures, and the “sent but not yet marked sent” scenario.
- Distinguish **at-least-once publication** from consumer-side exactly-once effects and eventual consistency.

This topic belongs to the **External Integration** group in Spring Framework Application Events. The focus is not only annotations, but **correctly designing transaction boundaries between Spring, the database, and external services**.

## 2. Define “guarantee” before choosing a solution

The phrase “publish externally after commit” has at least four requirement levels:

| Requirement | Interpretation | Typical mechanism |
| --- | --- | --- |
| Do not send on rollback | If the transaction fails, no external side effect is produced from that event | `AFTER_COMMIT` callback or outbox written inside the transaction |
| Only send after data commits | External systems can read the committed state at the source | Post-commit callback or outbox relay |
| Committed events are not lost on process crash | Durable evidence exists to retry after restart | **Transactional outbox** + relay/recovery |
| No duplicate side effects at the destination | Retries/redeliveries still do not create two invoices or two emails | **Consumer idempotency**, unique business keys, provider idempotency |

**`@TransactionalEventListener(AFTER_COMMIT)` meets the callback timing goal while the process stays alive**, but **does not provide durability on its own**. For critical business flows, a transactional outbox is the standard approach to solve dual writes without needing distributed transactions between the database and the broker.

A more precise definition for a reliable system:

> If and only if the business transaction commits successfully, the database must contain a corresponding event/outbox record. A recoverable relay will keep attempting to publish until there is proof the external system accepted it per the contract, assuming infrastructure recovers and the relay continues running. Duplicates can still occur; consumers must tolerate them.

This is a **conditional** guarantee, not a promise that “every event is always delivered exactly once under all circumstances” regardless of data loss, indefinite downtime, or missing consumers.

## 3. What does Spring ApplicationEventPublisher actually do?

A service can publish a POJO or Java record:

```java
public record OrderCommitted(
        String eventId,
        String orderId
) {}

publisher.publishEvent(
        new OrderCommitted("evt-100", "ORD-42"));
```

This is an integration snippet; `ApplicationEventPublisher publisher` must be declared. Spring Framework supports `publishEvent(Object)`; for objects that do not extend `ApplicationEvent`, Spring can wrap them in `PayloadApplicationEvent<T>` and dispatch them to `@EventListener` methods matching the payload type.

**This contract is publication within the application context**, not:

- Writing an event to a message broker.
- Writing an event to an event store.
- Guaranteeing retries after a crash.
- Guaranteeing that all listeners have finished processing by a certain point.
- Guaranteeing only-once/exactly-once delivery.
- Automatically synchronizing database transactions with Kafka/RabbitMQ/HTTP.

An adapter can listen to a local event and then send externally, but **a failure boundary still exists between the local event and the external broker** that must be handled.

### Three layers to separate mentally

```text
Business service
  |
  | publishEvent(OrderCommitted)
  v
Spring ApplicationEventMulticaster       <- local/in-process
  |
  v
@EventListener / @TransactionalEventListener
  |
  | KafkaTemplate.send / RabbitTemplate.convertAndSend /
  | HTTP client / email provider
  v
External system                          <- process/network boundary
```

Do not use the same word “publish” and inadvertently equate **local publish was called** with **the broker confirmed storing the message**.

## 4. Approach 1: @TransactionalEventListener(AFTER_COMMIT)

With Spring transactions managed by `PlatformTransactionManager` in a thread-bound application, a listener can bind to a transaction phase:

```java
@Component
public class OrderCommittedPublisher {
    private final ExternalEventGateway gateway;

    public OrderCommittedPublisher(ExternalEventGateway gateway) {
        this.gateway = gateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderCommitted event) {
        gateway.publish(event);
    }
}
```

This is an **integration pattern**, not a standalone runnable program: it requires `ExternalEventGateway` and appropriate imports. When `OrderCommitted` is published **inside an active transaction** and the transaction commits successfully, Spring invokes the callback after commit. On rollback, the `AFTER_COMMIT` callback is not called. If the event is published outside a transaction, the callback **does not run by default**, because `fallbackExecution = false`.

This is reasonable for **best-effort** tasks that do not require high durability—such as cache invalidation notifications that can be rebuilt, auxiliary metrics, or waking up another worker that already has durable work records.

### Basic lifecycle

```text
Transaction T1
    |
    +--> persist order
    +--> publishEvent(OrderCommitted)
    |
    +--> COMMIT succeeds
            |
            +--> @TransactionalEventListener(AFTER_COMMIT)
                     |
                     +--> gateway.publish(...)
```

**Important:** “the callback runs after commit” does not mean “the broker has definitely accepted the event”. If the gateway times out, returns an error, the process crashes, or the network is unstable, sending can still fail.

### 4.1. Transaction phases

| `TransactionPhase` | When does the callback run? | What is it used for? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit, when the commit can still fail | Validation/syncing work still belonging to the transaction; **unsuitable for sending external events requiring commit** |
| `AFTER_COMMIT` | After the transaction commits successfully | Best-effort signals; post-commit callbacks |
| `AFTER_ROLLBACK` | After the transaction rolls back | Cleanup/telemetry appropriate for rollbacks; avoid producing success effects |
| `AFTER_COMPLETION` | After the transaction finishes, whether commit or rollback | Outcome-based tracking/cleanup |

`@TransactionalEventListener` defaults to `AFTER_COMMIT`; writing `phase` explicitly helps readers understand intent. `AFTER_COMPLETION` is not the right choice if you only want to send “OrderCommitted” when the order actually committed, because it can also run on rollback.

### 4.2. fallbackExecution

Default:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = false)
public void handle(OrderCommitted event) {
    // ...
}
```

If there is no active transaction, the listener is not called. Enabling `fallbackExecution=true` allows the listener to run even without a source transaction; however, **it then no longer signifies confirmation that a source transaction committed**. For events that must only appear after commit, do not enable fallback just because you noticed the callback isn’t running—fix the publishing site to have a proper transaction or design a separate path.

### 4.3. Reactive transactions require different handling

Since Spring Framework 6.1, `@TransactionalEventListener` can also be used with reactive transactions, but the reactive pipeline’s transaction context resides in **Reactor Context**, not a standard `ThreadLocal`. That case requires an appropriate publication mechanism and event source/context, typically via `TransactionalEventPublisher`. Do not take an imperative snippet with `TransactionTemplate` and assume it behaves identically across WebFlux/R2DBC.

## 5. Limitations of AFTER_COMMIT

### 5.1. Event loss window

```text
T0  begin transaction
T1  update order
T2  publish local event (register after-commit callback)
T3  database COMMIT succeeds
T4  process crash                <- EVENT LOSS WINDOW
T5  callback never runs
T6  external broker does not know the order committed
```

Even when `@TransactionalEventListener` code is completely correct, notifications can still be lost at T4. The callback lives only in runtime memory; Spring does not automatically persist it to run after restart.

### 5.2. Network timeouts and indeterminate state

After commit, the gateway sends the message; if the request times out:

- The broker might **not have received** the event.
- The broker might **have received** the event, but the response was lost.
- The broker might only have buffered it without meeting the application’s durability requirements.

Do not automatically assign `SENT` or `FAILED` based solely on an exception without understanding the broker/provider’s **acknowledgment contract**. When the state is uncertain, retrying is usually the safe choice for at-least-once delivery, which introduces the possibility of duplicates.

### 5.3. Post-commit exceptions do not roll back an already-committed transaction

If an `AFTER_COMMIT` callback throws an exception, the already-committed business data will not roll back due to that exception. Callers might observe an exception on the commit path depending on infrastructure, but **the DB outcome and external send outcome have already diverged**. Do not design APIs assuming “catching a post-commit exception means the order can be treated as uncreated”.

### 5.4. Writing to the DB after commit requires a new transaction

Spring warns that inside post-commit callbacks, some transactional resources may still be bound to the thread. If you perform new DB access without starting a new transaction, the operation may “join” the old resource **without having another commit cycle**.

If you need to write a marker/notification-outbox inside the callback, use a separate service:

```java
@Service
public class FollowUpRecorder {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFollowUp(OrderCommitted event) {
        repository.save(...);
    }
}

@Component
public class AfterCommitHandler {
    private final FollowUpRecorder recorder;

    public AfterCommitHandler(FollowUpRecorder recorder) {
        this.recorder = recorder;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderCommitted event) {
        recorder.recordFollowUp(event);
    }
}
```

This is an **integration pattern**, requiring a repository and imports. `REQUIRES_NEW` must be called through a Spring proxy, not via self-invocation `this.recordFollowUp(...)`. Even if the new transaction commits successfully, this pattern **still has a loss window between the business commit and the recorder call**; it is not an end-to-end transactional outbox.

## 6. TransactionSynchronization.afterCommit: the low-level option

If you want direct callback control without annotations, Spring provides `TransactionSynchronizationManager.registerSynchronization(...)`:

```java
if (!TransactionSynchronizationManager.isSynchronizationActive()) {
    throw new IllegalStateException(
            "An active transaction synchronization is required");
}

TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                externalGateway.publish(event);
            }
        });
```

This is an **integration snippet**: it requires a proper active transaction, `externalGateway`, `event`, and imports for `TransactionSynchronizationManager` and `TransactionSynchronization`. In a real application, you must verify appropriate active transaction semantics rather than blindly copying this into a non-transactional method.

This mechanism is useful when you need a hook at the transaction synchronization level. However, **it shares the same in-RAM callback nature** and does not eliminate the post-commit crash window. `@TransactionalEventListener` is usually more readable and idiomatic when a bean wants to receive Spring domain events.

Do not confuse `TransactionSynchronization.afterCommit()` with `@Async` or durable messaging. If durable delivery to a broker is required, both must be backed by a transactional outbox.

## 7. Approach 2: Transactional outbox — persist send intent with the business transaction

**Transactional outbox** solves dual writes by not sending to the broker directly inside the business transaction. Instead, the service writes **both the business state and an outbox row in the same database transaction**. After commit, an independent **relay** reads the committed outbox and sends to external systems, retrying on errors.

```text
                  BUSINESS TRANSACTION (single DB)
BEGIN
   |
   +--> UPDATE orders SET status='CONFIRMED'
   |
   +--> INSERT event_outbox(
          event_id, aggregate_id, event_type, payload, status='PENDING')
   |
COMMIT  <--- order and outbox commit together or roll back together
   |
   v
Durable outbox row
   |
   +--> Relay worker polling / CDC
           |
           +--> broker.publish(eventId, payload)
           |        |
           |        +--> timeout/failure -> keep pending, retry
           |        |
           |        +--> confirmed -> mark SENT
           |
           v
      Kafka / RabbitMQ / webhook / external consumer
```

### Core atomic guarantee

Inside the source transaction:

- **Commit succeeds** → both order data and the outbox record exist durably.
- **Rollback** → neither a new order state nor an outbox row exists for that change.
- **Process crash after commit** → the outbox row remains; another worker can continue sending after restart.

Condition: the business state and the outbox must genuinely reside **in the same transaction of the same ACID storage engine**. If the service writes to database A and then writes the outbox to database B in another transaction, this atomicity no longer holds.

### 7.1. Transactional outbox does not automatically “send exactly once”

A relay can:

1. Successfully send an event to the broker.
2. Crash before updating `status = SENT`.
3. Restart and see the row is still `PENDING`.
4. Send the **same eventId** once more.

This is **at-least-once relay delivery**; consumers should use an idempotency key/unique constraint to discard duplicate side effects. Do not replace `eventId` with a new UUID on every retry if you want consumers to recognize **the same occurrence**.

### 7.2. Polling publisher and CDC

Two common ways for a relay to read the outbox:

| Mechanism | Principle | Considerations |
| --- | --- | --- |
| Polling | Worker periodically queries `PENDING` rows, claims, and sends | Polling latency, DB load, multi-worker claiming, retries |
| CDC / transaction-log tailing | Reads outbox changes from the DB commit log and forwards to broker | Connector operations, offsets, ordering, schemas, duplicate/repair |

Both require monitoring, idempotency, and recovery policies. CDC does not automatically turn broker + database into a single end-to-end exactly-once transaction for all consumers.

## 8. Designing a practical outbox schema

An example schema in a relational database:

```sql
CREATE TABLE orders (
    order_id       VARCHAR(80) PRIMARY KEY,
    status         VARCHAR(30) NOT NULL
);

CREATE TABLE event_outbox (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    event_type     VARCHAR(120) NOT NULL,
    payload_json   CLOB NOT NULL,
    status         VARCHAR(20) NOT NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL
);
```

This is a **design schema**, distinct from the simplified schema in the section 10 program. Key fields:

- `event_id`: immutable identifier for the occurrence, preserved across retries.
- `aggregate_id` + `aggregate_type`: supports routing, ordering, and traceability.
- `event_type` + `payload_json`: describes the message to be sent externally.
- `status`: e.g., `PENDING`, `IN_PROGRESS`, `SENT`, or `DEAD_LETTER` by design.
- `attempt_count` and retry timestamp: supports backoff/observability.
- `created_at` and aggregate version: useful if downstream needs ordering.

In multi-tenant applications, add `tenant_id` and keys/constraints appropriate to the event identifier scope. Do not log payloads containing secrets/PII merely for debugging.

### Status and claiming

With multiple relay workers, do not let every worker simultaneously query `WHERE status='PENDING'` and send right away **without claim coordination**. You can use time-bounded leases:

```text
PENDING -> CLAIMED (owner, lease_until) -> SENT
                    |
                    +--> timeout / worker crash -> retryable PENDING
                    |
                    +--> max attempts exceeded -> DEAD_LETTER
```

Some databases support `SELECT ... FOR UPDATE SKIP LOCKED`, or claiming via `UPDATE ... WHERE status='PENDING' ... RETURNING` depending on DB features. Use a short transaction to claim, commit the claim before calling the broker, and handle expired leases; **do not hold a DB lock across potentially slow HTTP/broker calls**.

### Ordering

`ORDER BY created_at` alone does not strictly guarantee event order across multiple workers, especially when timestamps collide or the first message is retried. If consumers require per-aggregate order, you need `aggregate_version`/sequence, per-aggregate partition keys, version-handling rules, and retry policies. **Idempotency and ordering are two separate contracts.**

## 9. Designing the outbound relay

A practical relay should have these phases:

1. **Find/claim** incomplete outbox rows using a mechanism that prevents duplicate claims across workers.
2. **Read an immutable payload snapshot** including `eventId`, key, type, version, and data.
3. **Send the message** to the broker/provider using a client properly configured for producer acknowledgments/confirmations.
4. **Wait for a sufficiently strong success signal per requirements**—not merely “called `send()`”.
5. **Mark `SENT` after acknowledgment**, in a separate update transaction.
6. On transient error, **keep/release the row as retryable** with exponential backoff and jitter.
7. On permanent schema/permission error, **move to a terminal/DLQ state** and alert.
8. Record metrics: `PENDING` count, oldest age, attempts, successes, duplicates, latency, and error rate.

### Kafka and RabbitMQ do not share the same confirmation API

- With Kafka, the send API is typically async; having a `Future` does not mean the broker has confirmed the message. You must handle completion/exceptions and configure the producer appropriately for your durability requirements.
- With RabbitMQ, publisher confirms and returned messages/routing policies are separate aspects. “Send did not throw immediately” does not necessarily mean the desired queue accepted it.
- With webhooks/HTTP, HTTP 2xx may mean “request received” rather than the target job completed. You need an API contract/idempotency key and reconciliation when responses are indeterminate.

**Do not record `SENT` immediately after calling an async send API without proper confirmation.** If you mark too early and the process dies, the message may never have been delivered while the outbox is already closed.

### Do not wrap all network I/O inside the source transaction

Trying to send to the broker directly inside the database transaction increases lock hold times, lowers throughput, and still fails to guarantee atomicity between DB and broker. The broker may ACK and then the DB rolls back; or the DB commits while the gateway state is uncertain. Outbox intentionally decouples the two systems to avoid pretending a single SQL transaction spans the network.

## 10. Complete Java 17 + Spring Framework 6.2 + JDBC/H2 example

The example below runs **in a single process** and uses a **simulated broker** to verify exact failure windows. The goal is to illustrate the **relationship between commit, outbox, and relay retries**, not to actually send to Kafka/RabbitMQ.

Scenario:

1. Commit order `ORD-100`, creating outbox `evt-100` in the same transaction.
2. Attempt to create `ORD-ROLLBACK` and roll back — **no order/outbox** is persisted and the `AFTER_COMMIT` callback does not run.
3. Relay sends `evt-100`: simulated broker fails the first time, row remains `PENDING`.
4. Relay retries: broker confirms success, row transitions to `SENT`.
5. Commit `ORD-300` with outbox `evt-300`.
6. Simulate “broker received `evt-300` but process died before marking `SENT`”. Row remains `PENDING`.
7. Relay sends `evt-300` again. Simulated broker records a **duplicate delivery**, while the receiver uses `eventId` to avoid creating another effect.
8. Outcome: two committed orders, two outbox rows, two unique event IDs accepted by the consumer, despite **four gateway calls**.

### 10.1. Project structure

```text
after-commit-outbox-demo/
├── pom.xml
└── src/main/java/example/AfterCommitOutboxDemo.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>after-commit-outbox-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.AfterCommitOutboxDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. src/main/java/example/AfterCommitOutboxDemo.java

```java
package example;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class AfterCommitOutboxDemo {

    public record OrderCommitted(String eventId, String orderId) {
        public OrderCommitted {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            if (eventId.isBlank() || orderId.isBlank()) {
                throw new IllegalArgumentException("ID must not be blank");
            }
        }
    }

    private record Pending(String eventId, String orderId) {}

    private static class SimulatedTransportFailure
            extends RuntimeException {
        SimulatedTransportFailure() {
            super("Simulated broker is unavailable");
        }
    }

    // Simulated broker/receiver; models ACK and idempotency only.
    public static class FakeGateway {
        private final Set<String> receivedIds = new LinkedHashSet<>();
        private int attempts;
        private int failures;
        private int duplicateDeliveries;

        public void send(String eventId, String orderId) {
            attempts++;

            // Only the first send attempt for evt-100 fails (simulated).
            if ("evt-100".equals(eventId) && failures == 0) {
                failures++;
                throw new SimulatedTransportFailure();
            }

            // Receiver deduplicates using eventId.
            if (!receivedIds.add(eventId)) {
                duplicateDeliveries++;
            }
        }

        public int attempts() {
            return attempts;
        }

        public int failures() {
            return failures;
        }

        public int duplicateDeliveries() {
            return duplicateDeliveries;
        }

        public int uniqueEvents() {
            return receivedIds.size();
        }
    }

    // Only a hint to wake the relay after commit; does not directly
    // send to the broker and does not serve as a durability source.
    public static class AfterCommitHint {
        private final AtomicInteger hints = new AtomicInteger();

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCommitted(OrderCommitted event) {
            hints.incrementAndGet();
        }

        public int count() {
            return hints.get();
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate businessTx;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate businessTx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.businessTx = businessTx;
            this.publisher = publisher;
        }

        public void commitOrder(
                String orderId, String eventId, boolean rollback) {
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO orders(order_id, status) "
                        + "VALUES (?, 'CONFIRMED')",
                        orderId);

                // Outbox is written in the SAME transaction as the order.
                jdbc.update(
                        "INSERT INTO event_outbox "
                        + "(event_id, order_id, event_type, status) "
                        + "VALUES (?, ?, 'OrderCommitted', 'PENDING')",
                        eventId, orderId);

                // Local event: post-commit callback only produces a hint.
                publisher.publishEvent(
                        new OrderCommitted(eventId, orderId));

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    // Single-worker relay: code illustrates semantics;
    // production requires claim/lease when multiple workers exist.
    public static class OutboxRelay {
        private final JdbcTemplate jdbc;
        private final FakeGateway gateway;

        public OutboxRelay(JdbcTemplate jdbc, FakeGateway gateway) {
            this.jdbc = jdbc;
            this.gateway = gateway;
        }

        private List<Pending> pendingRows() {
            return jdbc.query(
                    "SELECT event_id, order_id "
                    + "FROM event_outbox "
                    + "WHERE status = 'PENDING' ORDER BY event_id",
                    (rs, row) -> new Pending(
                            rs.getString("event_id"),
                            rs.getString("order_id")));
        }

        public void drainOnce() {
            for (Pending item : pendingRows()) {
                try {
                    // Send outside the DB transaction. Only treat
                    // gateway return as success (the demo's ACK).
                    gateway.send(item.eventId(), item.orderId());
                } catch (SimulatedTransportFailure expected) {
                    // Transient error: row stays PENDING for retry.
                    continue;
                }

                // Mark SENT only AFTER the gateway reports success.
                jdbc.update(
                        "UPDATE event_outbox SET status = 'SENT' "
                        + "WHERE event_id = ? AND status = 'PENDING'",
                        item.eventId());
            }
        }

        public void simulateAckBeforeMark(String eventId) {
            Pending item = pendingRows().stream()
                    .filter(p -> p.eventId().equals(eventId))
                    .findFirst()
                    .orElseThrow();

            // Send succeeds, then simulate a crash right here:
            // intentionally do NOT update status.
            gateway.send(item.eventId(), item.orderId());
        }

        public int pendingCount() {
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM event_outbox "
                    + "WHERE status = 'PENDING'",
                    Integer.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds =
                    new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:outbox_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate businessTx(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public FakeGateway fakeGateway() {
            return new FakeGateway();
        }

        @Bean
        public AfterCommitHint afterCommitHint() {
            return new AfterCommitHint();
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate businessTx,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, businessTx, publisher);
        }

        @Bean
        public OutboxRelay outboxRelay(
                JdbcTemplate jdbc,
                FakeGateway gateway) {
            return new OutboxRelay(jdbc, gateway);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);
            OutboxRelay relay = context.getBean(OutboxRelay.class);
            FakeGateway gateway = context.getBean(FakeGateway.class);
            AfterCommitHint hint = context.getBean(AfterCommitHint.class);

            jdbc.execute(
                    "CREATE TABLE orders ("
                    + "order_id VARCHAR(80) PRIMARY KEY,"
                    + "status VARCHAR(30) NOT NULL)");

            jdbc.execute(
                    "CREATE TABLE event_outbox ("
                    + "event_id VARCHAR(80) PRIMARY KEY,"
                    + "order_id VARCHAR(80) NOT NULL,"
                    + "event_type VARCHAR(100) NOT NULL,"
                    + "status VARCHAR(20) NOT NULL)");

            // T1 commits, T2 rolls back.
            service.commitOrder("ORD-100", "evt-100", false);
            service.commitOrder(
                    "ORD-ROLLBACK", "evt-rollback", true);

            // First simulated broker error; subsequent retry succeeds.
            relay.drainOnce();
            int pendingAfterFailure = relay.pendingCount();
            relay.drainOnce();
            int pendingAfterRetry = relay.pendingCount();

            // Second event commits with a durable outbox row.
            service.commitOrder("ORD-300", "evt-300", false);

            // Simulate: gateway receives but SENT is not marked yet.
            relay.simulateAckBeforeMark("evt-300");
            int pendingAfterAckBeforeMark = relay.pendingCount();

            // Worker retry may send duplicate; receiver deduplicates.
            relay.drainOnce();

            System.out.println("After first drain pending="
                    + pendingAfterFailure);
            System.out.println("After retry pending="
                    + pendingAfterRetry);
            System.out.println("After ack-before-mark pending="
                    + pendingAfterAckBeforeMark);
            System.out.println("Committed orders="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orders",
                            Integer.class));
            System.out.println("Outbox rows="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM event_outbox",
                            Integer.class));
            System.out.println("After-commit hints=" + hint.count());
            System.out.println("Gateway attempts=" + gateway.attempts());
            System.out.println("Transient failures=" + gateway.failures());
            System.out.println("Duplicate deliveries="
                    + gateway.duplicateDeliveries());
            System.out.println("Receiver unique events="
                    + gateway.uniqueEvents());
            System.out.println("Final pending=" + relay.pendingCount());
            System.out.println("Rolled-back rows="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orders "
                            + "WHERE order_id = 'ORD-ROLLBACK'",
                            Integer.class));
        }
    }
}
```

### 10.4. Run command

Using JDK 17+ and Maven, from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Twelve output lines printed by the program** in this demo design, excluding Maven/Spring logs if any:

```text
After first drain pending=1
After retry pending=0
After ack-before-mark pending=1
Committed orders=2
Outbox rows=2
After-commit hints=2
Gateway attempts=4
Transient failures=1
Duplicate deliveries=1
Receiver unique events=2
Final pending=0
Rolled-back rows=0
```

### 10.5. Why is each number right?

- `ORD-100` is written and committed with outbox `evt-100`, resulting in one `PENDING` row.
- The transaction for `ORD-ROLLBACK` calls `status.setRollbackOnly()`, rolling back both order and outbox. The `AFTER_COMMIT` listener for this event does not run.
- The first `relay.drainOnce()` calls the gateway for `evt-100`. `FakeGateway` intentionally throws `SimulatedTransportFailure` on the first send; the relay catches the transient error and keeps `PENDING`.
- The next `drainOnce()` sends `evt-100` successfully; the gateway adds the ID to the received set, and then the relay updates the outbox to `SENT`.
- `ORD-300` commits with outbox `evt-300` and adds another callback hint.
- `simulateAckBeforeMark("evt-300")` calls the gateway successfully but **does not update the DB**, simulating a process crash right between ACK and marking `SENT`. The outbox remains `PENDING`.
- The worker retries `evt-300`. The gateway receives another call, but the simulated receiver has an `eventId` set, detects the duplicate, and adds no new effect.
- Total `gateway.attempts() = 4`: one failed attempt for `evt-100`, one successful `evt-100`, one successful `evt-300` before mark, and one retry of `evt-300`.
- `failures = 1`, `duplicateDeliveries = 1`, and `receivedIds.size() = 2`.
- There are two business commits, so `AfterCommitHint` receives two callbacks. There is no callback for the rolled-back transaction.
- Finally, both outbox rows are `SENT`; no `PENDING` rows remain. Only `ORD-100` and `ORD-300` exist in the `orders` table.

### 10.6. Intentional limitations of the example

- `FakeGateway` is a broker/receiver simulation, **with no real network connection or delivery guarantee**. It treats a successful return from `send(...)` as the demo’s ACK.
- `LinkedHashSet` stores received IDs only within a single JVM. **Production requires durable deduplication at the consumer** if side effects must not repeat.
- H2 uses an in-memory database; when the JVM exits, data is not persisted across restarts. For real systems, use a persistent database and appropriate backup/replication mechanisms.
- `OutboxRelay` has only **a single sequential worker** and does not yet implement claim/lease, backoff, DLQ, or real broker producer confirmations.
- The example only simulates the crash window; **it does not actually kill the process**.
- The code uses `TransactionTemplate` to control commit/rollback without configuring `@Transactional` proxies. In applications using `@Transactional`, you still need a proper transaction manager and must avoid self-invocation.
- The `AfterCommitHint` callback only increments a counter and **does not send to the broker**, so it does not create a new dual-write window. Production can use hints to wake the relay, but must have independent polling/recovery when hints are lost.
- Hardcoded IDs are used so results are easy to verify; production must allocate a unique `eventId` per new event occurrence and preserve it across retries.
- Real systems must define external gateway acknowledgments and retry/idempotency policies per specific contracts.

**The most important point:** external events are sent by the **relay reading the committed outbox**, not by the `AFTER_COMMIT` callback. The callback only optimizes latency, while **the outbox row is the durable source of work**.

## 11. When to use a direct callback vs. an outbox?

| Criterion | `@TransactionalEventListener(AFTER_COMMIT)` calling gateway directly | Transactional outbox + relay |
| --- | --- | --- |
| Do not send on rollback | Yes, if transaction/callback are properly configured | Yes, because the outbox also rolls back |
| Implementation simplicity | Simpler | More components |
| Crash after commit before send | Can lose the event | Committed outbox remains |
| Extended broker downtime | Callback can fail with no durable retry | Relay retries from outbox |
| Possible duplicate messages | Possible if self-retried/source emits repeatedly | Yes; relay can repeat after ACK-before-mark |
| Long-term delivery guarantee | No, unless persistence/recovery is added | Conditional, while relay operates and infrastructure recovers |
| Suitable for critical notifications | Only if best-effort is acceptable | Usually more appropriate |
| Requires idempotent consumer | Yes, when retries/duplicates can occur | Yes, mandatory for non-repeatable effects |
| Latency | Can be short if callback runs immediately | Polling/CDC/hints affect latency |
| Operations | Monitor callbacks and gateway | Need to monitor backlog, claims, retries, DLQ |

**Practical choice:** if you only need to update auxiliary metrics and can tolerate occasional lost events, a post-commit callback may suffice. If you must notify billing, fulfillment, critical auditing, or external systems after every business commit, **prefer a transactional outbox** and verify reliability at every hop.

## 12. If you still want to publish a local event to wake the worker

A good hybrid model:

```text
OrderService transaction
    +--> save order
    +--> insert event_outbox
    +--> publishEvent(OutboxReadyHint)
             |
             v
        AFTER_COMMIT
             |
             +--> signal relay (best effort)
             |
             +--> poller/CDC remains the recovery path
```

The post-commit signal simply spares the worker from waiting until the next polling interval. If the signal is lost due to a crash, the poller still finds the durable row. In a multi-instance application, the relay must have **claim/lease coordination**; a signal from one instance does not guarantee that instance is the chosen worker.

Do not use the hint as **the sole path** for processing the outbox. If the hint has no listener or the listener dies, `PENDING` rows will pile up indefinitely. A periodic scan loop or CDC with checkpoints/recovery is required.

### Do not create a new root event just to retry

When replaying the same outbox row, use the **recorded `eventId`**. If every relay retry generates a new UUID, the consumer loses the ability to deduplicate the same event occurrence. If business logic creates a valid new command, a new ID may be warranted; distinguish new commands from replays.

## 13. How to handle transactions at each stage

This problem involves **three different transactions** that must not be conflated:

1. **Business transaction:** updates the order and writes the outbox event in the same commit.
2. **Relay claim/mark transaction:** acquires ownership to process a row and marks it after broker acknowledgment.
3. **Consumer transaction:** records the idempotency marker and internal effect in the receiving system.

```text
T1: UPDATE order + INSERT event_outbox  -> COMMIT
T2: CLAIM outbox row                    -> COMMIT
NETWORK: publish event + broker ACK
T3: MARK outbox SENT                    -> COMMIT
CONSUMER: INSERT processed + business effect -> COMMIT
```

You cannot place a single `@Transactional` over an entire network send method and expect the broker to automatically join the SQL transaction. When systems do not participate in the same distributed transaction protocol, there is no atomic commit across them.

### When marking SENT fails

The broker ACKed, but T3 fails or the process crashes → the outbox may remain `PENDING`/`CLAIMED`. When the lease expires, a worker retries and **may send a duplicate**. This is why consumers must be idempotent.

### When the broker times out

It is unknown whether the broker processed it. Do not mark `SENT`. Return the row to a retryable state with the same `eventId`/idempotency key; do not delete the row because of a timeout.

### When the consumer fails

The broker may have stored the message and acknowledged the producer successfully, yet the consumer has not processed it. The producer’s outbox may already be `SENT` per the broker contract; you need **consumer retries/DLQ and idempotency** at the receiving system. “Producer sent” does not mean “consumer business effect committed”.

## 14. Consumer-side idempotency

An example marker table:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer processes within a single transaction:

```text
BEGIN CONSUMER TRANSACTION
    INSERT processed_messages(consumer, eventId)
        -- unique conflict: duplicate -> rollback/skip
    UPDATE read_model / INSERT invoice
COMMIT
```

When the marker and database effect share the same transaction, an effect failure rolls back the marker, allowing the next retry to run again. The unique constraint protects against **two competing workers**; do not use a separate `SELECT exists` followed by `INSERT` without a unique key.

### Idempotency keys must match the business semantics

- `(consumer, eventId)` prevents processing the same occurrence twice for one consumer.
- A business key like `(tenantId, paymentId, invoiceType)` may require an additional unique constraint if **two different `eventId`s** still must not create two invoices.
- `correlationId` only groups a workflow and is usually not a deduplication key.
- `aggregateId` can have many valid events (`Created`, `Paid`, `Shipped`); do not use it alone as a key that blocks subsequent events.

If the side effect is HTTP/email, a DB marker alone is not enough for exactly-once: the external send can succeed and then time out before the marker commits. You need a target API with an idempotency key, a consumer-side outbox, or reconciliation while accepting an appropriate at-least-once contract.

## 15. Testing: verifying commit, rollback, and failure windows

### 15.1. Minimum test matrix

| Scenario | What must be asserted |
| --- | --- |
| Order commit succeeds | Order and outbox row with the same `eventId` exist |
| Transaction rollback | No new order, no outbox row, no `AFTER_COMMIT` callback |
| Publish local event outside transaction | Transaction-bound listener does not run when `fallbackExecution=false` |
| Crash after business commit | Outbox remains durable after restart on a persistent DB |
| Broker down | Row stays pending/retryable, not falsely marked `SENT` |
| Broker ACK succeeds | Marked `SENT` only after confirmation per contract |
| Crash after ACK before mark | Retry can resend the same `eventId` |
| Two relay workers claim concurrently | No lost work; coordination exists, duplicates handled by consumer |
| Consumer receives same `eventId` twice | Business effect is recorded only once |
| Poison message | Terminal/DLQ state and alert exist |
| Out-of-order events | Consumer checks version/sequence if needed |
| Queue backlog grows | Monitoring detects it, events are not silently dropped |

The section 10 program simulates part of this matrix: commit, rollback, single gateway failure, retry, ACK-before-mark, and receiver deduplication. It **does not replace integration tests with a real broker and persistent DB**.

### 15.2. Testing AFTER_COMMIT with Spring transactions

If a test uses `@Transactional` at the test-method level, Spring TestContext normally rolls back the test transaction after each test. An `AFTER_COMMIT` listener will then **not be invoked**, even though the code published the local event.

To test post-commit callbacks, use a genuinely committed transaction via `TransactionTemplate` or control the test-managed transaction with `TestTransaction.flagForCommit()` and `TestTransaction.end()`. Rollback tests must verify no effect occurred.

### 15.3. Do not use sleep to test retries

For async relays, use latches/futures with timeouts, a fake gateway counting attempts, and outbox state queries. Avoid `Thread.sleep(50)` followed by assertions; slow CI machines or full queues can make tests flaky.

### 15.4. When restart durability must be proven

Realistic test:

1. Start the application with a **persistent database**.
2. Inside a transaction, write order + outbox and commit.
3. Stop the process **before the relay sends**.
4. Start a new session and verify the relay finds the `PENDING` row again.
5. Make the broker time out and then recover; ensure eventual send.
6. Stop the process after ACK before mark; confirm no event loss and consumer deduplication.
7. Verify the final count of business effects matches requirements.

That is real evidence of crash resilience; do not extrapolate it from an in-memory H2 demo.

## 16. Monitoring and operations runbook

Recommended metrics:

- `outbox_pending_count` by event type and tenant/partition where appropriate.
- `outbox_oldest_pending_age_seconds`: age of the oldest unsent row.
- `outbox_publish_attempts_total`, `outbox_publish_success_total`, `outbox_publish_failure_total`.
- `outbox_claim_expired_total`: number of expired leases needing reclaim.
- `broker_publish_ack_latency` and timeout rate.
- `consumer_duplicates_skipped_total`.
- `dead_letter_count`, `schema_validation_failure_total`.
- `relay_instance_heartbeat` or CDC connector health.
- Time from `business_commit -> broker_ack` (end-to-end publication lag).

Logs should include `eventId`, `aggregateId`, `eventType`, `correlationId`, `attempt`, `relayWorkerId`, `status`, and permissible broker/topic names. Do not log full payloads containing secrets or PII.

### Short runbook when the external system does not see an event

1. Check whether the business transaction actually committed.
2. Search for the outbox row by `eventId`; if absent, investigate transaction code or source workflow.
3. If a `PENDING` row exists, inspect lease, `next_retry_at`, and relay heartbeats.
4. If the row is `SENT`, check producer confirmations and the message ID on the broker.
5. If the broker has the message, check consumer offsets/ACK/DLQ/idempotency.
6. If duplicates occurred, check the ACK-before-mark window and retry policy.
7. Do not blindly “replay all events” when consumers have non-idempotent side effects.
8. When backfilling, preserve `eventId`/tenant/schema version and record the operational action.

## 17. Common mistakes

1. **Sending to the broker inside `@Transactional` and thinking the broker rolls back with the DB.** Two systems do not automatically share one commit.
2. **Using a regular `@EventListener` and sending before the transaction commits.** Can create ghost events.
3. **Using `@TransactionalEventListener(AFTER_COMMIT)` and claiming “zero event loss”.** In-RAM callbacks still have a crash window.
4. **Setting `fallbackExecution=true` because the listener wasn’t running.** It can run untethered from a source commit.
5. **Writing to the DB inside a post-commit callback without opening a new transaction.** The old resource may have no subsequent commit.
6. **Assuming an exception in a post-commit listener rolls back business state.** The business transaction has already committed.
7. **Writing the outbox after commit in another transaction and treating it as atomic with business state.** Leaves a loss window between the two transactions.
8. **Calling the broker directly from the relay and marking `SENT` as soon as the async send method returns.** No proper ACK yet.
9. **Assuming producer ACK means the consumer succeeded.** Two independent steps.
10. **Generating a new `eventId` on retries.** Consumer cannot recognize the same occurrence.
11. **Marking `SENT` before the broker confirms.** Can lose events.
12. **Holding a DB row lock across network sends.** Increases contention and transaction duration.
13. **No claim/lease when running multiple relay workers.** Two workers can send the same row concurrently; consumer idempotency becomes even more critical.
14. **Catching all SQL errors and treating them as duplicates.** Can mask connection outages or other constraints.
15. **Using only a `processed_messages` table without a business unique key.** Two different `eventId`s can still produce duplicate business effects.
16. **Not controlling ordering.** Two events with different versions for one aggregate can arrive out of order.
17. **Sending raw JPA entities in payloads.** Risks lazy loading, mutable state, and schema coupling.
18. **Only logging status information.** Insufficient for crash recovery.
19. **Using an H2 in-memory test and claiming restart durability is proven.** In-memory DBs lose data when the process exits.
20. **No DLQ/alerting.** Poison messages can block queues or retry endlessly.
21. **Ignoring partition/tenant keys.** A message can go to the wrong tenant or break aggregate ordering.
22. **Relying solely on a wake-up hint without polling/recovery.** Signals can be lost.
23. **Forgetting that the broker also has its own retention/replication failure modes.** Outbox protects the source, not every limit at the destination.
24. **Treating idempotency as protection against event loss.** It prevents duplicate effects, not unpersisted missing events.

## 18. Production deployment checklist

- [ ] Requirements defined: no ghost events, no lost events, retry/latency bounds, and durability level.
- [ ] Every event has a stable `eventId`, `eventType`, aggregate key, and appropriate version/correlation metadata.
- [ ] Business state and **event outbox share one ACID transaction**.
- [ ] Business transaction rollback also rolls back the outbox.
- [ ] Relay fetches rows from the **committed outbox**, not relying solely on in-RAM callbacks.
- [ ] Claim/lease in place for multiple workers, retries with backoff/jitter, and DLQ.
- [ ] Producer confirmations implemented accurately per actual broker/provider.
- [ ] `SENT` marked only after proper confirmation; timeouts remain retryable.
- [ ] Retries/replays preserve `eventId` and tenant scope.
- [ ] Consumers use an idempotency marker along with business unique constraints where needed.
- [ ] Ordering/version checks implemented where the domain requires them.
- [ ] Local `@TransactionalEventListener(AFTER_COMMIT)`, if used, is only a hint or best-effort.
- [ ] New DB accesses from post-commit callbacks open a new transaction when needed.
- [ ] Local Spring events are not confused with broker publication.
- [ ] Tested commit/rollback, gateway errors, ACK-before-mark, worker crashes, and restarts.
- [ ] Tested multi-worker contention, consumer deduplication, and indeterminate network failures.
- [ ] Metrics exist for backlog, oldest pending, retries, failures, DLQ, and publication lag.
- [ ] Safe reprocess/backfill runbook exists without duplicating sensitive side effects.
- [ ] Payloads are versioned, sensitive data minimized, and broker permissions controlled.

**Remember:** `@TransactionalEventListener(AFTER_COMMIT)` guarantees the **timing** of a callback in-process once a transaction commits, but does not by itself guarantee durable delivery. To **ensure external publishing after commit** even when the process or broker temporarily fails, **persist an outbox in the business transaction**, use a **recoverable retrying relay** to send only committed events, and handle duplicates via **consumer idempotency**.

## References

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework 6.2 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Transactional Outbox Pattern — microservices.io](https://microservices.io/patterns/data/transactional-outbox.html)
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
