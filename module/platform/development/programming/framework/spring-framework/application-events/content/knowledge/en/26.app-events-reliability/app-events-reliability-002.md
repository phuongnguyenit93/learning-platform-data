# Duplicate Events in Practice with Spring Application Events

## 1. The Problem: A Single Fact Can Be Processed Multiple Times

In an event-driven system, **a business fact occurring once does not mean the event handler code is invoked only once**. For an event like `OrderPaid`, the sender may resend after a timeout, a message broker may redeliver because it did not receive an acknowledgement, an outbox relay may restart after sending but before recording status, or a bug may emit another event reporting the same outcome.

Example:

```text
10:00:00  Payment confirmed -> OrderPaid(eventId=E-101, orderId=O-42)
10:00:01  Consumer receives E-101 -> creates fulfillment order for O-42
10:00:02  Consumer completes fulfillment but ACK fails
10:00:05  Consumer receives E-101 again
10:00:06  Without deduplication: creates a second fulfillment
```

Repeating an event does not always cause a bug. A handler that merely sets `status=PAID` on a record to the exact same value may be naturally idempotent. However, a handler performing `balance = balance - amount`, `sendEmail()`, `createShipment()`, or `issueRefund()` usually produces extra side effects if called again.

**The goal of reliability:** accept that deliveries can repeat, define which *business effect* must occur at most once, and make the consumer safe to retry. The most important technique is **idempotency**: re-executing the same request/event does not change the business outcome a second time.

In Spring, distinguish between:

- `ApplicationEventPublisher.publishEvent(...)` in **Spring Framework** is an in-process/in-context event dispatch mechanism; by default listeners are synchronous, and it does not automatically provide a persistent queue, retries, or exactly-once delivery.
- When an application uses a broker, transactional outbox, Spring Modulith Event Publication Registry, or additional retry logic, **the same occurrence can be reprocessed**.
- When publisher code calls `publishEvent(...)` twice, the listener is called twice even without a broker. This happens because there were two publishes, not because Spring automatically double-publishes.

Do not try to eliminate all duplicates in the infrastructure and assume the business logic is already safe. **Idempotency must be defined at the consumer and the actual side-effect boundary.**

## 2. Two Types of Duplicates Often Confused

### 2.1. Duplicate of One Event Occurrence (Redelivery/Replay)

Two deliveries with the same `eventId`:

```json
{"eventId":"e-101","type":"OrderPaid","orderId":"O-42"}
{"eventId":"e-101","type":"OrderPaid","orderId":"O-42"}
```

Under a proper contract, `eventId` identifies **one occurrence of a fact**. When a broker redelivers that exact fact, the producer/relay must **preserve the same eventId**. The consumer can record that it has already processed this ID.

If each retry generates a new UUID, a consumer relying solely on `eventId` will not recognize that it is the same fact.

### 2.2. Duplicate Business Effect Despite Different eventIds

Example:

```json
{"eventId":"e-101","type":"OrderPaid","orderId":"O-42"}
{"eventId":"e-202","type":"OrderPaid","orderId":"O-42"}
```

There are two different event IDs, yet both state that order `O-42` has been paid. This could be a publisher bug, a re-executed business command, or two valid facts modeled imprecisely.

If the effect is **creating a single fulfillment per paid order**, deduplicating by `eventId` is **not enough**. You need an additional business constraint, such as `UNIQUE(order_id)` on the fulfillment table or a key like `FULFILL:<orderId>`.

**However, do not discard every new event just because it shares the same orderId.** An order can have multiple partial payments, refunds, adjustments, or two genuinely distinct fulfillment packages. You must define "once" accurately by business semantics: `orderId`, `paymentId`, `shipmentId`, `invoiceId`, or the pair `(aggregateId, operationType)`.

### 2.3. Multiple Subscribers Processing the Same Event Is Not a Bug

`OrderPaid` being handled by Audit, Fulfillment, and Analytics represents **three independent subscribers**, not three duplicate executions by one subscriber.

If processed IDs are stored in a shared table, the appropriate key is usually:

```sql
PRIMARY KEY (subscriber_id, event_id)
```

If you only use `event_id` as a global key across all consumers, the Fulfillment subscriber running first could accidentally make the Audit subscriber think the event was already processed. Deduplication must be **scoped**.

## 3. Distinguishing Duplicate Messages, Duplicate Facts, and Duplicate Side Effects

| Type | Example | Is it a bug? | Primary control |
| --- | --- | --- | --- |
| Duplicate delivery | Broker redelivers E-101 after ACK timeout | Can be normal at-least-once behavior | Processed event ID per subscriber |
| Duplicate publish of same occurrence | Relay resends the same E-101 | Can happen after crash/retry | Preserve ID, idempotent consumer |
| Duplicate business event | E-101 and E-202 both say the same order is Paid | Must reconcile semantics | Business invariant/unique effect key |
| Multiple valid subscribers | Audit and Fulfillment both receive E-101 | **No** | Separate processed state per subscriber |
| Repeated legitimate operation | Two genuine payment captures with two payment IDs | **May be valid** | Do not wrongly discard based only on orderId |
| Duplicate side effect | Same order unexpectedly creates two shipments | Usually a business bug | Transaction + UNIQUE + external idempotency |
| Replayed historical event | Rebuild read model from event log | May be an intended operation | Clear replay mode, versioning, idempotency |

In documentation and metrics, clearly specify the counting unit: *delivery attempts*, *event occurrences*, *consumer executions*, or *business effects*. A dashboard that only shows "duplicate count" without a definition is very hard to use during an incident.

## 4. Where Do Duplicates Arise in Practice?

### 4.1. Producer Retry After Timeout

A producer sends a message; the broker receives it, but the connection drops before the producer sees the ACK. The producer retries. If the retry uses the same message/event ID, downstream can deduplicate it. If the retry creates a new fact with a new UUID, downstream also needs to check a business key.

### 4.2. Consumer Crash After Side Effect, Before ACK

```text
Broker -> Consumer -> DB commit succeeds
                      |
                      +-- JVM crashes before ACK
Broker sees no ACK -> redelivers the same message
```

You cannot infer from "processed" in logs that the broker recorded the ACK. The consumer must be safe when receiving the message again.

### 4.3. Outbox Relay Crashes in an Inconvenient Window

Transactional outbox writes business state and the record to publish **in the same transaction**, reducing the risk of losing events if the producer dies between DB commit and publish. However, the relay may send the message to the broker and then crash before marking the outbox row as sent:

```text
DB transaction:  update order + save outbox E-101 -> COMMIT
Relay:           publish E-101 -> broker ACK
Relay:           CRASH before marking sent
Relay restarts:  sees E-101 not marked sent -> publishes E-101 again
```

**Outbox solves the message-loss window, not duplicate delivery.** Consumers still need idempotency.

### 4.4. Event Registry and Resubmission

Spring Modulith includes an **Event Publication Registry** to persist publications for transactional listeners and mark completion. If a listener fails or the process stops at a sensitive stage, the publication can be resubmitted depending on the mechanism and configuration of the version in use. A listener may finish the side effect and crash before the registry marks it completed.

Therefore, the registry **does not replace handler idempotency**. It provides tracking/recovery for publications, but cannot automatically turn every external side effect into exactly-once.

### 4.5. Listener Registration Bugs, Parent-Child Contexts, Manual Publish

In a Spring application without a broker, check for:

- Calling `publishEvent(...)` for the same event in two places.
- A publisher retried at the service layer without using a business idempotency key.
- Multiple listener classes/beans unintentionally performing the same effect.
- A context hierarchy; events from a child context can propagate to the parent and be received in different scopes.
- A listener publishing a nested event, creating an unexpected callback flow.
- A scheduled job replaying business data without gating already-completed items.

Do not conclude "Spring ApplicationEventPublisher retries on its own" just because a listener logs twice. Inspect **publisher call sites, message IDs, context IDs, listener bean identities, and retry boundaries** first.

## 5. At What Level Should Idempotency Live?

There are two critical layers that usually must be used together.

### 5.1. Event-ID Deduplication — Reprocessing the Same Message

Example table:

```sql
CREATE TABLE processed_messages (
    subscriber_id VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (subscriber_id, event_id)
);
```

Consumer `fulfillment-v1` receives E-101:

1. Start transaction.
2. `INSERT` `(subscriber_id="fulfillment-v1", event_id="E-101")`.
3. On uniqueness conflict: this event occurrence is already completed under this contract; roll back/skip.
4. If the insert succeeds: apply the business change **in the same transaction**.
5. Commit both the processed marker and the effect.

If it rolls back before commit, the processed marker rolls back too; a subsequent delivery can retry. If commit succeeds and ACK fails, the next delivery sees the processed marker and skips the side effect. This is the idempotent consumer pattern.

**Critical condition:** the marker and business effect must share the same transaction or have an equivalent coordination mechanism. Writing the marker in Redis and transferring money in a different DB without atomicity opens a new failure window.

### 5.2. Business Idempotency — One Effect At Most Once

For example, a paid order may only create one fulfillment:

```sql
CREATE TABLE fulfillment_effects (
    effect_key     VARCHAR(120) PRIMARY KEY,
    first_event_id VARCHAR(80) NOT NULL
);
```

With key `FULFILL:O-42`, both E-101 and E-202 collide on the same unique key. This is an **effect-based** protection layer, distinct from storing delivered event IDs.

Use both when needed: processed messages prevent reprocessing the same occurrence, while business keys protect invariants even if a publisher creates an invalid new occurrence.

### 5.3. Key Correctness Matters More Than Storage Technology

| Side effect | Usually reasonable idempotency key | Risk when chosen poorly |
| --- | --- | --- |
| Write one audit row per event occurrence | `(subscriberId,eventId)` | Missing audit rows when collapsing distinct events |
| Create one fulfillment for a fully paid order | `(orderId,fulfillmentType)` | Duplicate fulfillment or wrongly blocking valid shipments |
| Send one notification per fact per channel | `(eventId,notificationChannel)` | Duplicate sends, or blocking email/SMS across channels |
| Charge one payment attempt | Stable `paymentAttemptId` / provider idempotency key | Double charge if relying only on a new eventId |
| Transfer money in a ledger | Stable transaction reference with uniqueness | Double debit/credit on replay |
| Trigger one callback per subscriber | `(subscriberId,eventId)` | One subscriber causes another subscriber to skip |
| Set projection to a specific version | `(aggregateId,version)`, ordering rules | Losing newer updates or overwriting with stale events |

Do not choose a key just because it is easy to grab from the payload. First define the **business unit allowed to occur once**, then select the fields and unique constraint.

## 6. False-Safety Deduplication Solutions

### 6.1. Using Only an In-Memory Set

```java
Set<UUID> seen = ConcurrentHashMap.newKeySet();

@EventListener
public void on(OrderPaid event) {
    if (!seen.add(event.eventId())) return;
    sendShipmentRequest(event.orderId());
}
```

This snippet is a **counterexample** inside a bean with application-defined `OrderPaid` and `sendShipmentRequest`. It has three problems:

1. A JVM restart wipes the Set; multiple instances have separate Sets.
2. If `sendShipmentRequest` throws an error **after `Set.add` succeeds**, retries are skipped even though the effect never completed.
3. If the external request succeeds and the listener fails before recording state, the Set alone cannot tell whether retrying is safe.

`ConcurrentHashMap.newKeySet()` prevents concurrent corruption of the Set itself, **not lack of atomicity between the Set and the side effect**.

### 6.2. SELECT Then INSERT Without a Unique Constraint

```java
if (!repository.existsByEventId(eventId)) {
    repository.saveProcessed(eventId);
    doBusinessEffect();
}
```

Two workers can both see "not present" before either writes. This is a **check-then-act** race. You need a constraint in the data store or a concurrency control mechanism with equivalent guarantees.

### 6.3. Marking Processed Before the Side Effect

```text
write processed=true -> COMMIT
call external API      -> timeout/failure
retry                  -> sees processed=true -> SKIP
```

The system loses its chance to execute the effect. A marker should only represent completion under the proper contract, or else you need `PENDING/PROCESSING/COMPLETED` states with recovery.

### 6.4. Executing Side Effect Then Writing Marker in Two Separate Transactions

```text
call external API      -> success
CRASH
write processed marker -> did not happen in time
retry                  -> calls external API again
```

With an external API, you cannot wrap everything in one local DB transaction. You need an **idempotency key at the target service** or explicit reconciliation/compensation.

### 6.5. Swallowing DuplicateKeyException Too Broadly

Not every `DuplicateKeyException` means "this event was already processed". It can come from:
- Duplicate invoice ID caused by a bug.
- Invalid business code.
- A conflict in another table.
- A constraint added later.

Scope the try/catch around inserting the **specific idempotency/effect key**, or inspect the constraint name/error source when the backend supports it. Never swallow every `DataIntegrityViolationException` and return "duplicate ignored".

## 7. Does Spring ApplicationEventPublisher Guarantee Exactly-Once?

**No.** Spring Framework Application Events is primarily a dispatch mechanism to listeners within an application context. It does not automatically persist publications, ACK message brokers, retry whole side effects, or deliver exactly-once guarantees.

By default, `SimpleApplicationEventMulticaster` dispatches listeners synchronously on the calling thread. If a listener throws an exception without a suppressing handler, the publisher may receive the error. A caller retrying the entire business operation after an exception can cause the event to be published again. If an executor/`@Async` is configured, listener errors can occur after the publisher has already returned.

Messaging systems may offer at-least-once, at-most-once, or transactional/exactly-once features within **a defined boundary**. Even when a broker guarantees once-only within its record/offset boundary, **crediting a DB, sending email, or calling a third-party API still requires its own idempotency design**. Never say "Kafka exactly once" and conclude every operation outside Kafka runs strictly once.

A realistic goal is an **effectively-once business effect**: the handler may be called multiple times, yet the final business state matches a single valid execution.

## 8. Runnable Spring Framework 6.2 + JDBC + H2 Example

The following example uses:

- **Java 17+**.
- **Spring Framework 6.2.12**: `spring-context`, `spring-jdbc`, and included transaction support.
- **H2 2.3.232**: in-memory database to demonstrate unique constraints and rollback/commit.
- **Maven**: compiles and runs the `demo.DuplicateEventDemo` class.

The example intentionally publishes the same business fact **three times**:

1. First E1: updates fulfillment once.
2. Repeated E1: **redelivery** of the same occurrence, must skip.
3. E2 with different eventId but same order: **duplicate effect** in the demo's domain, must skip.

Unlike using a Set, the marker and fulfillment count are updated in **a single DB transaction** under a unique constraint. The listener distinguishes a duplicate eventId from a different eventId by checking the initial record.

### 8.1. Structure

```text
duplicate-event-demo/
├── pom.xml
└── src/main/java/demo/DuplicateEventDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>duplicate-event-demo</artifactId>
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
                <configuration>
                    <mainClass>demo.DuplicateEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DuplicateEventDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class DuplicateEventDemo {

    public record OrderPaid(
            UUID eventId,
            String orderId,
            Instant occurredAt) {
        public OrderPaid {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            if (orderId.isBlank()) {
                throw new IllegalArgumentException("blank orderId");
            }
        }
    }

    // NOT final: Spring creates a transactional proxy for the service.
    public static class FulfillmentService {
        private final JdbcTemplate jdbc;

        public FulfillmentService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void fulfill(OrderPaid event) {
            String key = "FULFILL:" + event.orderId();

            // UNIQUE effect_key blocks both same eventId and new eventId.
            jdbc.update(
                    "INSERT INTO fulfillment_effects "
                    + "(effect_key, first_event_id) VALUES (?, ?)",
                    key, event.eventId().toString());

            int changed = jdbc.update(
                    "UPDATE orders "
                    + "SET fulfillment_count = fulfillment_count + 1 "
                    + "WHERE order_id = ?",
                    event.orderId());

            if (changed != 1) {
                // Roll back the effect_key record too if the order is missing.
                throw new IllegalStateException("missing order");
            }
        }
    }

    public static final class FulfillmentListener {
        private final FulfillmentService fulfillmentService;
        private final JdbcTemplate jdbc;

        public FulfillmentListener(
                FulfillmentService fulfillmentService, JdbcTemplate jdbc) {
            this.fulfillmentService = fulfillmentService;
            this.jdbc = jdbc;
        }

        @EventListener
        public void on(OrderPaid event) {
            String key = "FULFILL:" + event.orderId();
            try {
                // Must call via Spring bean proxy for @Transactional to apply.
                fulfillmentService.fulfill(event);
                System.out.println("FULFILLED order=" + event.orderId());
            } catch (DuplicateKeyException duplicate) {
                // Example only: duplicate error could come from another constraint.
                // In this code, the first INSERT is the operation with a UNIQUE key.
                String firstEventId = jdbc.queryForObject(
                        "SELECT first_event_id "
                        + "FROM fulfillment_effects WHERE effect_key = ?",
                        String.class, key);

                if (event.eventId().toString().equals(firstEventId)) {
                    System.out.println(
                            "REDELIVERY_SKIPPED order=" + event.orderId());
                } else {
                    System.out.println(
                            "BUSINESS_DUPLICATE_SKIPPED order=" + event.orderId());
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:dedupe;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        FulfillmentService fulfillmentService(JdbcTemplate jdbc) {
            return new FulfillmentService(jdbc);
        }

        @Bean
        FulfillmentListener fulfillmentListener(
                FulfillmentService service, JdbcTemplate jdbc) {
            return new FulfillmentListener(service, jdbc);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute(
                    "CREATE TABLE orders ("
                    + "order_id VARCHAR(40) PRIMARY KEY, "
                    + "fulfillment_count INT NOT NULL)");

            jdbc.execute(
                    "CREATE TABLE fulfillment_effects ("
                    + "effect_key VARCHAR(120) PRIMARY KEY, "
                    + "first_event_id VARCHAR(36) NOT NULL)");

            jdbc.update(
                    "INSERT INTO orders (order_id, fulfillment_count) "
                    + "VALUES (?, ?)",
                    "O-100", 0);

            UUID original =
                    UUID.fromString("00000000-0000-0000-0000-000000000001");
            UUID another =
                    UUID.fromString("00000000-0000-0000-0000-000000000002");
            Instant at = Instant.parse("2026-01-01T00:00:00Z");

            context.publishEvent(new OrderPaid(original, "O-100", at));
            context.publishEvent(new OrderPaid(original, "O-100", at));
            context.publishEvent(new OrderPaid(another, "O-100", at));

            Integer count = jdbc.queryForObject(
                    "SELECT fulfillment_count FROM orders "
                    + "WHERE order_id = ?",
                    Integer.class, "O-100");

            Integer effectRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM fulfillment_effects",
                    Integer.class);

            System.out.println("FULFILLMENT_COUNT=" + count);
            System.out.println("EFFECT_ROWS=" + effectRows);
        }
    }
}
```

Run from the `duplicate-event-demo` directory:

```bash
mvn -q compile exec:java
```

Lines printed by the program **in order** (excluding Spring/Maven logs):

```text
FULFILLED order=O-100
REDELIVERY_SKIPPED order=O-100
BUSINESS_DUPLICATE_SKIPPED order=O-100
FULFILLMENT_COUNT=1
EFFECT_ROWS=1
```

### 8.2. Why Can the Example Prevent Duplicates?

1. `AnnotationConfigApplicationContext` creates the context, registers `@EventListener`, and enables `@Transactional` infrastructure.
2. Calling `publishEvent(OrderPaid)` uses a plain Java record; Spring Framework supports POJO event payloads. Listeners are invoked synchronously by default, so stdout has a deterministic order.
3. On the first call, `FulfillmentService.fulfill(...)` goes through the transactional proxy to start a DB transaction; it inserts `FULFILL:O-100` and increments `fulfillment_count` from 0 to 1 in the same transaction.
4. The second call with the **same eventId** hits the primary key on `fulfillment_effects.effect_key`. `DuplicateKeyException` exits the transactional method and the transaction rolls back. The listener reads the committed `first_event_id` and prints `REDELIVERY_SKIPPED`.
5. The third call with a **different eventId** for the same order hits the effect key again; the listener prints `BUSINESS_DUPLICATE_SKIPPED`.
6. The orders table still has `fulfillment_count=1`; the effects table has exactly one row. No second increment occurred.

### 8.3. Limitations of the Demo

- Both `orders` and `fulfillment_effects` belong to **the same H2 database**, so a local transaction protects both.
- There is no HTTP, broker, thread pool, retry policy, or external shipment API; the event is published directly three times to **intentionally** reproduce duplicates.
- The "duplicate" classification logging in the listener is illustrative. In a real system, catch the exact constraint and enforce the business key contract.
- H2 is created in memory; restarting the JVM loses data. Replace with a durable DB in production.
- `FULFILL:<orderId>` is only valid for a domain allowing **one fulfillment of that type per order**. With multiple packages, multiple shipments, or partial fulfillment, the key must include the appropriate discriminator.
- If the effect calls an external carrier API, a DB transaction cannot guarantee the carrier will not create two shipments on a network timeout. You need an **external idempotency key** and reconciliation.
- If the system has multiple replicas, a unique constraint in the same authoritative database is a better coordination mechanism than a Set in each JVM. You must use the right database/partition and ensure tenant-scoped uniqueness if IDs are not globally unique.

**Why not catch all exceptions and treat them as duplicates?** Because other errors like DB connection loss, invalid SQL, or a missing order must be surfaced clearly, not disguised as "already processed". The example catches only `DuplicateKeyException`, and in a real system you should isolate the unique insert operation to know which constraint was violated.

## 9. Commit Boundaries: Handling Errors Before and After Writing Markers

Suppose a consumer processes `OrderPaid(E-101)`.

### 9.1. Error Before Transaction Commit

```text
BEGIN
  INSERT processed_messages(subscriber, E-101)
  UPDATE projection
  -- error, ROLLBACK
END
```

Both the marker and projection roll back together, so a subsequent redelivery can reprocess. This is a key property of transactional idempotency design.

### 9.2. Worker Dies After Commit

```text
BEGIN
  INSERT processed_messages(subscriber, E-101)
  UPDATE projection
COMMIT
CRASH before ACK
```

Redelivery sees the primary key already exists and skips the effect. **You do not need to avoid redelivery; you need to make redelivery harmless.**

### 9.3. Side Effects in External Systems

```text
BEGIN local DB
  INSERT processed marker
COMMIT
HTTP POST /shipments -> external service created shipment
CRASH before saving response
retry -> risk of creating a second shipment
```

An internal transaction does not protect a side effect in another service. Approaches:

- Send a stable key, such as `fulfillment:O-42`, as an idempotency key if the target API supports it.
- The target must store the key and result, returning the prior result on valid retries.
- If the API does not support it, design a state machine + reconciliation (looking up shipments by business reference) or compensation. Do not treat `HTTP 500/timeout` as proof the target did not process the request.
- Maintain a durable outbox/queue for side-effect requests and deduplication at the final consumer.
- Separate the "request sent" state from "business effect confirmed".

Especially for money, email, shipping, or outbound notifications, identify the **effect unit** that must be idempotent right where the effect happens.

## 10. TransactionalEventListener and Duplicates

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` ensures a listener only runs after the original transaction commits successfully:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPaid event) {
    fulfillOrder(event);
}
```

This is an illustrative snippet inside a Spring bean with a valid transaction manager and `fulfillOrder` method, not part of the runnable code in section 8.

However, remember:

- `AFTER_COMMIT` **does not automatically create a persistent event queue**.
- Process death after commit but before or during the callback can still lose processing without a registry/outbox.
- When a callback is retried/resubmitted by another mechanism, the side effect can still run multiple times.
- A post-commit callback that wants to write to the DB as a new transaction may need `REQUIRES_NEW` on a proper service/proxy.
- Transaction synchronization is not synonymous with "exactly-once delivery".
- If an event is published without a transaction, transactional listeners do not run by default unless `fallbackExecution=true` is configured.

### Spring Modulith Event Publication Registry

Spring Modulith can store publication records for transactional listeners and mark completion. Incomplete publications can be resubmitted according to configuration/APIs. Operations teams must monitor pending/failed/resubmitted publications to resolve incidents.

Example duplicate window:

```text
Business transaction commits + publication record stored
  |
  v
Listener finishes side effect
  |
  +-- CRASH before registry marks COMPLETED
         |
         v
Resubmit incomplete publication
         |
         v
Listener invoked again -> idempotent effect must SKIP
```

Features and API names vary by Spring Modulith version (especially across releases with specific publication statuses). Use documentation for **your project's exact version**; do not mix newer registry APIs into a project that only uses Spring Framework core.

## 11. Designing an Idempotent Consumer with Multiple Workers

Example of two workers receiving the same event E-101:

```text
Worker A: SELECT processed -> none
Worker B: SELECT processed -> none
Worker A: INSERT + process
Worker B: INSERT + process
```

If you only `SELECT` and then save without uniqueness, both can execute the side effect. Therefore:

1. Use `PRIMARY KEY/UNIQUE` in the authoritative store.
2. Perform atomic insert/claim inside a transaction or a compare-and-set with verified semantics.
3. Do not rely on a distributed lock as the sole mechanism for exactly-once if side effects and lock state lack atomicity.
4. Ensure database uniqueness matches the tenant/subscriber/business key.
5. With composite keys, check partition boundaries: uniqueness in one shard does not prevent duplicates in another shard if the same entity is misrouted.

### Uniqueness Enforcement Matters More Than Pre-Checking

A "check then insert" pattern can help return an early error message, but **the database constraint is the final safeguard** when multiple workers contend. A race may cause code to attempt an insert and hit a conflict; that conflict is the expected outcome of idempotency and should not be paged as a SEV-1 for every routine duplicate.

### Do Not Assume Global Ordering

Message E2 may arrive before E1 under async execution, replay, or repartitioning. If effects must be applied by aggregate version, ordering/version rules are needed:

```text
OrderPaid(version=5)    -> projection version 5
OrderCancelled(version=6)-> projection version 6
Old OrderPaid(version=5) arrives later
                         -> do not overwrite version 6
```

Deduplicating by `eventId` **does not automatically handle out-of-order events**. Consumers may need expected aggregate versions, optimistic locking, or a state machine that ignores stale events and waits for missing ones.

## 12. Event ID, Correlation ID, Causation ID, and Business Key

| Field | Purpose | Should it be used for deduplication? |
| --- | --- | --- |
| `eventId` | Identifies a specific occurrence | **Yes** for redelivery of the same occurrence |
| `subscriberId` | Scopes a single consumer | **Yes** when combined with eventId |
| `businessKey` | Identifies a business effect | **Yes**, if the invariant is defined accurately |
| `orderId` | Aggregate identity | **Not necessarily**; multiple valid events can share an order |
| `paymentId` | Payment attempt/transaction | Usually good for deduplicating payments per contract |
| `correlationId` | Groups steps of a workflow | **No**; one workflow has many events |
| `causationId` | Points to what caused the fact | Does not replace eventId/business key |
| `traceId` | Links traces in observability | **No**; many events share a trace |
| `occurredAt` | Timestamp when it happened | Insufficient as a key; can collide and suffer clock skew |

Do not use `correlationId` as a deduplication ID. A checkout request can produce `OrderPlaced`, `PaymentCaptured`, and `InventoryReserved` with the same correlation, yet each fact and side effect is distinct.

### A New UUID on Retry Can Break Duplicate Semantics

If a retry is **resending the same event**, keep the original `eventId`. If the retry actually creates a **new fact** per domain decision, it needs a new event ID. These two kinds of retries must be separated clearly.

## 13. Preventing Duplicates at the Producer

Consumer deduplication is necessary, but it does not excuse a producer emitting false duplicate facts.

At the producer, a business command may need:

- An `idempotencyKey` for HTTP requests (supplied by the caller per contract, validated).
- Persisting the command result by idempotency key in the database.
- Optimistic locking/version checks to prevent double state transitions like PAID -> PAID.
- Unique constraints on payment attempts/transaction references.
- A domain invariant rejecting "capture money a second time" when invalid.
- An outbox row in the same transaction as business state for durable publication.
- A stable `eventId` for a recorded fact.

Conceptual example:

```text
POST /payments/capture
Idempotency-Key: capture-P-900

First request:
  verify authorization
  capture payment once
  persist result and event ID E-101
  return captured

Retry with same key:
  return prior result
  do not capture again
  do not manufacture a new business fact
```

This is an **example contract**, not an HTTP header automatically provided by Spring. If a client sends the same key with a completely different payload, detect the conflict per API policy rather than silently returning an old result for a different request.

Even with an idempotent producer, relays or consumers can still observe duplicate deliveries, so additional deduplication layers are not redundant.

## 14. Retention, Replay, and Schema Evolution

A `processed_messages` table cannot grow forever without a retention policy. However, purging markers too early can cause replaying an old message to recreate a side effect.

Before setting a TTL, know:

- How long does the broker retain messages at most?
- Does the system perform manual replays months later?
- How long can the outbox/registry resubmit outstanding publications?
- Within what time window can a side effect legitimately recur?
- Are there audit/ledger rules requiring longer retention?
- If the business key is durable enough, can unique effect keys be kept longer than event-level markers?

For unrepeatable effects, a **durable business invariant** usually matters more than a short-TTL eventId cache.

If the event schema evolves, consumers must know how to read historical payloads and idempotency keys. Renaming `paymentId` or changing key generation logic without migrating state can allow replays to slip past deduplication.

### Intentional Replay Differs from Production Duplicate Handling

Sometimes replay is used to rebuild a new read model. If a new listener has a new subscriber ID, receiving historical events again can be completely valid. However, a listener sending emails/charging cards **must not** accidentally execute production side effects in a replay environment.

Separate read-model replays from effectful consumers, or use a replay mode with policies blocking external side effects. Never rely solely on an untrusted message's `isReplay` flag to decide whether to bypass authorization.

## 15. Observing Duplicates and Failure Windows

To debug effectively, record at minimum:

- `eventType`, `eventId` (or an appropriate hash/opaque ID).
- Validated `subscriberId` and `businessEffectKey`.
- Necessary `tenantId`/scope without excessive PII.
- Attempt number if provided by transport; do not pretend it is a global processing count.
- Outcome: `APPLIED`, `DUPLICATE_SKIPPED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`.
- Latency/queue age against defined milestones.
- Exception cause when the error is not a duplicate.
- Source: producer double publish, outbox resend, broker redelivery, registry resubmission, or manual replay when evidence exists.

Example structured logs:

```text
eventType=OrderPaid eventId=E-101 subscriber=fulfillment
effectKey=FULFILL:O-42 outcome=APPLIED

eventType=OrderPaid eventId=E-101 subscriber=fulfillment
effectKey=FULFILL:O-42 outcome=REDELIVERY_SKIPPED

eventType=OrderPaid eventId=E-202 subscriber=fulfillment
effectKey=FULFILL:O-42 outcome=BUSINESS_DUPLICATE_SKIPPED
```

**Be careful with metrics:** do not put raw `eventId/orderId/customerId` as tags on every counter/timer because cardinality is huge. Use low-cardinality `eventType`, `subscriber`, `outcome`, and `errorClass` (with an allowlist). Put detailed IDs in properly access-controlled logs/traces.

### What Does a Rising Duplicate Rate Signal?

Depending on the source:

- Rising broker redeliveries: slow listener, ACK timeouts, or consumer crashes.
- Rising outbox resends: relay crashes, failing to update sent status, or network errors.
- Rising new business duplicate IDs: weak command idempotency or publisher bug.
- Rising `BUSINESS_DUPLICATE_SKIPPED` after deploy: the new key definition may be too broad, blocking valid effects.
- Duplicates disappear while side effects disappear: possibly caused by writing markers before effects, `DiscardPolicy`, or swallowed exceptions.

**Never optimize the duplicate rate to 0 by dropping logs or silently discarding tasks.** The goal is correct processing and easy diagnostics, not hiding symptoms.

## 16. Testing Real Deduplication

A test suite must prove both **processed once** and **retriable after failure**.

| Scenario | Expectation |
| --- | --- |
| E1 published for the first time | Effect is created once |
| E1 republished with the exact same ID | Effect count does not increase |
| E2 different ID but same business key | No second effect created if invariant allows only one |
| E2 different ID, different business key | New valid effect is still created |
| DB error after inserting marker before commit | Marker + effect roll back; subsequent retry can succeed |
| Worker crashes after DB commit before ACK | Redelivery recognizes completion and does not repeat effect |
| Two workers process E1 concurrently | Unique constraint blocks duplicate effect |
| Publisher retries with stable idempotency key | Does not emit an invalid new business fact |
| Same event to two subscribers | Each subscriber handles its own part without cross-blocking |
| Out-of-order events | Consumer uses appropriate version/state machine |
| External API timeout after processing | Retry uses stable idempotency key or reconciliation |
| Process restart | DB marker remains if using a persistent store |
| Manual replay | Consumer side effect is not wrongly re-executed |
| Tenant A/B share the same local ID | Dedupe scope and DB routing isolate tenants properly |

### 16.1. JUnit with the Spring/JDBC Example

You can put the demo's dispatch logic into a test and assert:

```java
context.publishEvent(new OrderPaid(e1, "O-100", at));
context.publishEvent(new OrderPaid(e1, "O-100", at));
context.publishEvent(new OrderPaid(e2, "O-100", at));

assertEquals(1, jdbc.queryForObject(
        "SELECT fulfillment_count FROM orders WHERE order_id = ?",
        Integer.class, "O-100"));

assertEquals(1, jdbc.queryForObject(
        "SELECT COUNT(*) FROM fulfillment_effects",
        Integer.class));
```

This is a **JUnit snippet** (requiring JUnit Jupiter dependency, `context`, `jdbc`, `e1/e2/at`), not the runnable file from section 8. Checking DB effects matters more than just counting how many times a listener was called.

### 16.2. Tests Must Not Assert Publish Count Alone

With Spring TestContext and `@RecordApplicationEvents`:

```java
long published = events.stream(OrderPaid.class).count();
```

This may return 3 if the test publishes three times, yet **does not** prove the DB prevented duplicates. The recorder checks the publisher path, while idempotency must be verified in the side-effect/state store. If the listener is async, tests must await outcomes with timeouts and probe the right boundary.

### 16.3. Testing Real Concurrency

Do not use `Thread.sleep(50)` hoping "two workers will contend". Use a `CountDownLatch` to synchronize start timing, run two tasks, wait on `Future.get()`/timeouts, and assert a single effect. If relying on DB locking/transactions, test on a database with production-equivalent isolation/constraints; in-memory H2 behavior does not prove all PostgreSQL/MySQL/Oracle semantics in every configuration.

### 16.4. Testing Non-DB Failures

Use a fake external API that can "succeed and then report a timeout" to verify retries with the same idempotency key. This is the hardest failure window: an exception/timeout on the client does not prove downstream failed to complete the operation.

## 17. Diagnostic Playbook for Production Duplicates

**Step 1 — Identify what is duplicated.** Same eventId or different eventIds? One subscriber or multiple subscribers? Real duplicate side effects or just duplicate logs?

**Step 2 — Locate the publication source.** Correlate timestamps and IDs across producer, outbox, broker, registry, and consumer; do not conclude based solely on log line counts.

**Step 3 — Find the retry boundary.** Request retry, transaction retry, outbox relay restart, broker redelivery, consumer retry policy, or manual replay?

**Step 4 — Cross-check ACK/commit.** Had the DB effect committed when the ACK was lost? Did the marker commit? Was there a network timeout after the remote service executed?

**Step 5 — Inspect the idempotency key.** Is a stable eventId used? Subscriber scoping? Does the business effect key distinguish legitimate operations?

**Step 6 — Look for races.** Check-then-insert without constraint? Multiple replicas/threads? Side effects executed outside a transaction?

**Step 7 — Check transaction proxies.** Is `@Transactional` actually applied? Is self-invocation bypassing the proxy? Do marker and effect share the same DataSource/transaction?

**Step 8 — Check prior failures.** Was a marker written too early, preventing retries? Were errors swallowed or logged as false successes?

**Step 9 — Check external idempotency.** Does the target service store the idempotency key? Is the key preserved across retries? Is reconciliation needed?

**Step 10 — Add reproduction tests.** Same event ID, different event ID with same business key, concurrency, rollback, crash window, replay, and multi-tenant scope.

### Symptom Table

| Symptom | Likely cause | Verification |
| --- | --- | --- |
| Same eventId appears twice at subscriber | Broker/outbox/registry resend | Producer/relay/ACK logs |
| Different eventId with same business key | Producer created fact twice or workflow re-invoked | Business command state, unique key |
| DB effect count = 2 | Missing unique constraint or non-atomic transaction | Schema, isolation, code path |
| Only duplicate email sent, DB row still one | External side effect is not idempotent | Notification key/provider |
| Processed marker exists with no effect | Mark-before-effect or separate transactions | Transaction audit, error path |
| Retries never reprocess | Marker wrongly written before completion | Recovery/marker semantics |
| Audit subscriber skips event handled by Fulfillment | Dedupe key not scoped by subscriber | PK/unique key |
| Occasionally processed twice under high load | Check-then-act race or multiple instances | Concurrency test, uniqueness |
| Many notifications sent after manual replay | Replay mode does not isolate side effects | Replay policy, consumer isolation |
| Two trace/log lines but only one effect | Redelivery was properly skipped | Effect state, outcome metrics |

## 18. Common Mistakes

1. **Assuming an event is always delivered once.** Brokers, outboxes, and retries can redeliver.
2. **Assuming Spring core automatically retries every ApplicationEvent.** Check additional application mechanisms.
3. **Using a new UUID on each resend of the same occurrence.** Defeats event-level deduplication.
4. **Using only an in-JVM `Set`.** Lost on restart and not synchronized across replicas.
5. **Calling `Set.add` before the side effect and forgetting the failure path.** Mid-way errors lose retries.
6. **SELECT-then-INSERT without a constraint.** Races between workers.
7. **Writing processed marker and business effect in two separate transactions.** Leaves a window for lost or duplicated effects.
8. **Calling an external API after local commit and assuming the DB transaction protects the API.** No cross-system atomicity exists.
9. **Using eventId to deduplicate every business effect.** A new eventId violating the same invariant can slip through.
10. **Using orderId to deduplicate all event types.** Can block other valid transactions on the same order.
11. **Not scoping by subscriber.** One consumer causes another consumer to skip.
12. **Conflating correlationId with eventId.** One workflow has many distinct facts.
13. **Treating `@TransactionalEventListener` as a durable queue.** Post-commit callbacks do not solve crash windows.
14. **Believing an outbox prevents duplicates.** Relays can publish multiple times on crashes.
15. **Believing broker exactly-once applies to every external side effect.** Guarantees have boundaries.
16. **Catching every DuplicateKeyException and returning success.** Masks other schema errors.
17. **Retrying infinitely on invalid payloads.** Poison events need policies and dead-letter handling.
18. **Not tracking event age, attempts, and outcomes.** Makes stuck publications hard to detect.
19. **Using PII-bearing IDs as metric labels.** High cardinality and data exposure risk.
20. **Purging processed IDs too early.** Old replays can recreate side effects.
21. **Not testing concurrency.** Code passes in one thread but fails with two workers.
22. **Confusing repeated event logs with double charges.** Verify actual effect state.
23. **Not distinguishing genuine repeated operations from duplicates.** Drops legitimate business operations.
24. **Lacking reconciliation for external APIs after timeouts.** Cannot tell whether execution completed.

## 19. Duplicate Prevention Design Checklist

- [ ] Are **event occurrence**, **delivery attempt**, and **business effect** clearly defined?
- [ ] Do retries of the same occurrence preserve `eventId`?
- [ ] Is deduplication scoped by subscriber and, if needed, tenant?
- [ ] Does the business effect have a unique key matching the real invariant?
- [ ] Is unsynchronized `contains` followed by `insert` avoided as a uniqueness guarantee?
- [ ] Are the processed marker and DB side effect in one transaction with a unique constraint?
- [ ] If the effect is in an external system, is there a stable idempotency key or reconciliation?
- [ ] Does the producer have business command idempotency and protection against emitting false facts?
- [ ] Have failure windows in event routing/outbox/registry/broker been checked?
- [ ] Are routine duplicates logged differently from severe errors?
- [ ] Does the consumer avoid swallowing non-duplicate errors?
- [ ] Have retries after rollback and replays after commit been tested?
- [ ] Are there tests for same eventId, different eventId with same key, and valid different keys?
- [ ] Are there concurrency tests on production-like databases/transports?
- [ ] Is deduplication retention long enough for valid replays/retries?
- [ ] Are production side effects prevented during manual replays?
- [ ] Are there outcome metrics, alerts for backlog/failed events, and safely correlated logs?
- [ ] Is "exactly once" avoided unless the guarantee boundary is explicitly stated?

**Conclusion:** Duplicate events in practice are usually part of the recovery model: after timeouts, crashes, or replays, producers and consumers may not know whether an effect completed. In Spring Application Events, publishing twice invokes listeners twice; once you add an outbox, broker, or Event Publication Registry, redeliveries must be handled deliberately. The durable approach is **a stable event ID per occurrence**, **per-subscriber idempotency**, **business unique keys for side effects**, **atomic transactions with business data**, and **idempotency/reconciliation at external services**. Accept multiple handler invocations, while protecting business outcomes from duplication.

## References

- [Spring Framework — Application Events and ApplicationEventPublisher](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Modulith — Working with Application Events and Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Microservices.io — Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [H2 Database documentation](https://h2database.com/html/main.html)
