# Designing Replayable Listeners

## 1. The Problem: The Same Event Processed Multiple Times

In Spring Framework Application Events, a listener often reacts to a business occurrence:

~~~java
@EventListener
public void onOrderPaid(OrderPaid event) {
    reportingService.addRevenue(event.orderId(), event.amountCents());
}
~~~

The illustrative snippet above risks **double-counting revenue** if the same `OrderPaid` is delivered to the listener again. That can happen because:

- An operator **replays events** to rebuild reports or repair drifted data.
- A consumer retries after a timeout, unsure whether the previous attempt committed.
- A message broker provides **at-least-once delivery**, delivering the same message again.
- A worker crashes after persisting results but before sending an ACK.
- A migration/reindexing process re-reads event history.
- A bug in the producer or consumer sends the same fact multiple times.
- The application itself calls `publishEvent(...)` a second time with the **same event identity**.

A **replayable / retry-safe listener** is designed to reprocess the same fact without producing incorrect side effects, while still processing genuinely new events. In many cases, the most important property is **idempotency**: repeating the same valid operation does not change the observable outcome beyond the first successful execution.

Distinguish clearly:

1. **Retry:** re-running work that failed or had an unknown outcome.
2. **Redelivery:** the source re-sends an old message/event, possibly even after a prior success.
3. **Replay:** re-reading a stored set of historical events to reconstruct a projection or recover a consumer.
4. **Rebuild:** recreating derived state from history or a source of truth, often into a new projection version.
5. **Reconciliation:** comparing and correcting discrepancies between a projection and the source data.

All five scenarios involve "running again," yet their requirements for **history storage, ordering, markers, and side effects** are not identical.

## 2. First Limitation: Spring Application Events Do Not Retain History Automatically

`ApplicationEventPublisher.publishEvent(...)` hands the event to the `ApplicationContext` dispatch mechanism. With the default `SimpleApplicationEventMulticaster`, plain listeners execute synchronously on the publishing thread unless the application configures an executor, `@Async`, or another mechanism.

~~~text
Service
  |
  +-- publishEvent(OrderPaid E1)
             |
             +--> @EventListener ReportingListener
             +--> @EventListener AuditListener
             +--> @Async NotificationListener (if configured)
~~~

**Default Spring application events have no durable event log, offsets, ACKs, or automatic replay button.** When the process restarts, Spring does not automatically re-read events published in a previous run.

To actually replay, you need a **readable replay source**, such as:

- an event store / append-only event log;
- a transactional outbox with an appropriate retention policy;
- a message broker retaining history for an allowed retention window;
- business tables plus a process generating **synthetic rebuild events** from source state (which must be distinguished from raw original history).

In this guide, we build a Spring example with an `event_archive` table to **illustrate manual replay within one process**. The demo's in-memory H2 database does not survive restarts; production requires a durable database/broker and a dedicated transactional consistency mechanism.

Do not assume that because a listener has `@EventListener` or `@TransactionalEventListener`, Spring will automatically retry when the method fails. By default, exception handling depends on the multicaster/async/transaction phase and application configuration; **retry policies must be explicitly designed**.

## 3. Event Identity: Same Event or a New Fact?

Example of an immutable event:

~~~java
public record OrderPaid(
    java.util.UUID eventId,
    long orderId,
    long amountCents
) {}
~~~

Identifiers to distinguish:

| Field | Interpretation | Use as Deduplication Key? |
| --- | --- | --- |
| `eventId` | Identity of **one recorded occurrence** | Usually the primary key for deduplicating the same occurrence |
| `orderId` / `aggregateId` | Entity/aggregate the occurrence relates to | Insufficient: one order can have multiple payments |
| `correlationId` | Ties operations to the same workflow/request | Insufficient: a workflow can emit multiple events |
| `causationId` | Event/command that caused the current event | Insufficient: one cause can lead to multiple outcomes |
| `deliveryAttempt` | Delivery attempt number (if transport provides one) | No: changes on each retry |
| `schemaVersion` | Data contract version | Does not replace event identity |

**Retrying the same occurrence must keep the same `eventId`.** If each retry generates a new UUID, the consumer treats it as a different fact and adds it again.

Conversely, **two distinct payments on the same order** must have two different event IDs. Using `orderId` as the deduplication key can drop a legitimate second payment.

~~~text
E1: eventId=111..., orderId=101, amount=500
  -> 1st processing: +500
  -> replay E1     : +0

E2: eventId=222..., orderId=101, amount=200
  -> 1st processing: +200 (a different occurrence)

Correct total for both occurrences: 700, not 500 or 1,200.
~~~

If a producer emits the **same `eventId` with a different payload**, that violates the identity/immutability contract; do not silently treat the new version as a safe duplicate. Production systems should have validation or payload fingerprint/version policies to detect conflicts.

## 4. Idempotent Side Effects and Processed Markers

A common strategy is an **inbox/processed-events table** recording which consumer has processed which event:

~~~text
processed_events
+-----------------+--------------------------------------+
| consumer_name   | event_id                             |
+-----------------+--------------------------------------+
| revenue-report  | E1                                   |
| audit-projector | E1                                   |
| revenue-report  | E2                                   |
+-----------------+--------------------------------------+
PRIMARY KEY (consumer_name, event_id)
~~~

Why is the key **(consumer, eventId)** instead of just `eventId`?

One event can be handled by multiple independent listeners. Just because `AuditListener` processed E1 **does not mean** `RevenueListener` has finished. Each consumer needs its own marker namespace. During rebuilds, you may also need `projectionVersion` or a fresh namespace/target.

The right pattern for side effects in the **same database**:

~~~text
BEGIN transaction
  INSERT processed_events(consumer, eventId) [unique constraint]
  UPDATE/INSERT reporting_projection (...)
COMMIT transaction
~~~

If the same `(consumer, eventId)` already committed, duplicates are skipped. If the transaction fails before commit, both the **marker and the projection update roll back**, so a retry can process it cleanly.

**You must atomically commit the marker and the business effect.** Two broken patterns:

- **Commit the marker first, then write the projection:** a crash between steps leaves the event marked done while the side effect never happened.
- **Commit the projection first, then write the marker:** a crash causes the retry to add/insert the data a second time.

When the side effect targets an **external system** (sending email, calling a payment provider, HTTP API), the two systems usually cannot share one transaction. In that case, an internal processed marker **does not guarantee an exactly-once external effect**: you need a destination-side idempotency key, an outbox/worker, a retry protocol, and reconciliation.

## 5. Four Ways to Make a Listener Replayable

### 5.1 Naturally Idempotent Operations

Instead of:

~~~java
// May double-count on replay:
revenueRepository.incrementTotal(event.amountCents());
~~~

A projection storing **latest state** by key/version can use a conditional upsert:

~~~text
Projection event: CustomerTierChanged(customerId, version=8, tier=GOLD)

UPDATE customer_tier
SET tier = 'GOLD', source_version = 8
WHERE customer_id = 101 AND source_version < 8;
~~~

This is conceptual SQL: missing rows and concurrency must be handled with your DB's actual upsert/constraints/locking. Updating by **monotonically increasing version** prevents old events from re-applying stale state; correctness depends on the aggregate's version contract.

For cumulative operations (money totals, loyalty points), an explicit marker or unique effect ID is normally needed because `x += amount` is not naturally idempotent.

### 5.2 Per-Event Unique Constraints

For example, a table `revenue_entries(event_id PRIMARY KEY, amount_cents)`. Inserting E1 again is rejected by the DB. Summing across unique entries will not double-count. Pros: minimal extra state. Cons: each side effect may span multiple tables and requires handling duplicate/key conflicts in the right places.

### 5.3 Processed Marker + Transaction

A `processed_events(consumer_name, event_id)` table with a unique key, plus the effect in the **same transaction**. This is easy to reason about for JDBC/JPA projections, provided everything requiring atomicity resides in the same datasource/transaction manager.

### 5.4 Inbox/Outbox and Durable Consumer State

A broker may deliver the same message multiple times. The consumer uses an inbox marker and a local transaction for idempotent processing; if it must call an external system, it writes an outbox message in the same transaction and a worker delivers it with an idempotency key.

~~~text
Broker redelivery E1
        |
        v
Consumer transaction
  +-- dedup E1
  +-- update local projection
  +-- create outgoing outbox item
        |
        v
Commit + ACK broker
        |
        v
Outbox delivery to external API (stable key E1)
~~~

Broker ACK must generally occur **after commit**; if a crash occurs after commit before ACK, the message is redelivered and the marker skips it. If ACK happens before commit, a crash can lose the side effect. Exact ACK behavior depends on the broker/client; follow your transport's contract.

## 6. Runnable Example: Replaying the Same Event Without Multiplying Results

This demo uses **Java 17+**, **Spring Framework 6.2.19**, **Spring JDBC**, and **H2 2.3.232**. It runs a **real Spring Application Event listener** inside `AnnotationConfigApplicationContext`, not a test manually invoking listener methods.

We create three tables:

~~~sql
CREATE TABLE event_archive (
    seq BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL UNIQUE,
    order_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE revenue_entries (
    event_id VARCHAR(36) PRIMARY KEY,
    order_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL
);
~~~

In the code:

- `EventArchive` saves occurrences with a fixed `eventId`, then publishes them.
- `RevenueListener` processes inside a `TransactionTemplate` with a dedicated transaction, writing **processed marker + revenue entry**.
- Tables enforce unique keys to guard against duplicates.
- `FailureGate` intentionally throws an exception **after inserting into both tables in the transaction but before commit**. H2 rolls back both inserts, so replay can safely re-apply.
- `EventArchive.replayAll()` reads history by `seq` and re-publishes with the **exact same `eventId`**.

**Crucial limitation:** the demo writes the archive and publishes in two separate steps, **without guaranteeing atomicity with a business transaction**. H2 is also in-memory: closing the process loses history. This demonstrates idempotency + replay within a single run; see Section 10 for a production outbox.

### 6.1. Structure

~~~text
replayable-event-listener/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ReplayableListenerDemo.java
    └── test/java/demo/ReplayableListenerDemoTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'replayable-event-listener'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-jdbc:6.2.19'
    implementation 'com.h2database:h2:2.3.232'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ReplayableListenerDemo'
}

test {
    useJUnitPlatform()
}
~~~

### 6.4. src/main/java/demo/ReplayableListenerDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class ReplayableListenerDemo {

    public record OrderPaid(
        UUID eventId,
        long orderId,
        long amountCents
    ) {
        public OrderPaid {
            Objects.requireNonNull(eventId, "eventId");
            if (orderId <= 0 || amountCents <= 0) {
                throw new IllegalArgumentException(
                    "Invalid paid order event"
                );
            }
        }
    }

    @Bean
    DataSource dataSource() {
        JdbcDataSource dataSource = new JdbcDataSource();
        // Each context/test gets its own in-RAM database.
        String name = UUID.randomUUID().toString()
            .replace("-", "");
        dataSource.setURL(
            "jdbc:h2:mem:replay_" + name + ";DB_CLOSE_DELAY=-1"
        );
        dataSource.setUser("sa");
        dataSource.setPassword("");
        return dataSource;
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
    FailureGate failureGate() {
        return new FailureGate();
    }

    @Bean
    EventArchive eventArchive(
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher) {

        jdbc.execute("""
            CREATE TABLE event_archive (
                seq BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                event_id VARCHAR(36) NOT NULL UNIQUE,
                order_id BIGINT NOT NULL,
                amount_cents BIGINT NOT NULL
            )
            """);

        jdbc.execute("""
            CREATE TABLE processed_events (
                consumer_name VARCHAR(80) NOT NULL,
                event_id VARCHAR(36) NOT NULL,
                PRIMARY KEY (consumer_name, event_id)
            )
            """);

        jdbc.execute("""
            CREATE TABLE revenue_entries (
                event_id VARCHAR(36) PRIMARY KEY,
                order_id BIGINT NOT NULL,
                amount_cents BIGINT NOT NULL
            )
            """);

        return new EventArchive(jdbc, publisher);
    }

    @Bean
    RevenueListener revenueListener(
            EventArchive archive,
            JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager,
            FailureGate gate) {

        // Depending on EventArchive ensures the schema has been created.
        // Do not use archive inside the listener: one source, two roles.
        return new RevenueListener(jdbc, transactionManager, gate);
    }

    public static final class FailureGate {
        private final AtomicBoolean armed = new AtomicBoolean();

        public void failNextProcessing() {
            armed.set(true);
        }

        public void failIfArmed() {
            if (armed.compareAndSet(true, false)) {
                throw new IllegalStateException(
                    "simulated transient failure"
                );
            }
        }
    }

    public static final class EventArchive {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public EventArchive(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        public void appendAndPublish(OrderPaid event) {
            // Demo version: write archive first, then publish.
            // Production must design dedicated transactional consistency.
            jdbc.update(
                "INSERT INTO event_archive" +
                "(event_id, order_id, amount_cents) VALUES (?,?,?)",
                event.eventId().toString(),
                event.orderId(),
                event.amountCents()
            );
            publisher.publishEvent(event);
        }

        public void replayAll() {
            List<OrderPaid> history = jdbc.query(
                "SELECT event_id, order_id, amount_cents " +
                "FROM event_archive ORDER BY seq",
                (rs, row) -> new OrderPaid(
                    UUID.fromString(rs.getString("event_id")),
                    rs.getLong("order_id"),
                    rs.getLong("amount_cents")
                )
            );
            history.forEach(publisher::publishEvent);
        }

        public int archivedCount() {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM event_archive",
                Integer.class
            );
        }
    }

    public static final class RevenueListener {
        private static final String CONSUMER = "revenue-report";

        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;
        private final FailureGate gate;

        public RevenueListener(
                JdbcTemplate jdbc,
                PlatformTransactionManager transactionManager,
                FailureGate gate) {

            this.jdbc = jdbc;
            this.transaction = new TransactionTemplate(
                transactionManager
            );
            // Isolate consumer's local transaction from the caller.
            this.transaction.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW
            );
            this.gate = gate;
        }

        @EventListener
        public void onOrderPaid(OrderPaid event) {
            try {
                transaction.executeWithoutResult(status -> {
                    // UNIQUE (consumer_name, event_id):
                    // an event is applied only once for this consumer.
                    jdbc.update(
                        "INSERT INTO processed_events" +
                        "(consumer_name, event_id) VALUES (?,?)",
                        CONSUMER,
                        event.eventId().toString()
                    );

                    jdbc.update(
                        "INSERT INTO revenue_entries" +
                        "(event_id, order_id, amount_cents)" +
                        " VALUES (?,?,?)",
                        event.eventId().toString(),
                        event.orderId(),
                        event.amountCents()
                    );

                    // Throw after both INSERTs but before COMMIT.
                    // Transaction rolls back both marker and effect.
                    gate.failIfArmed();
                });
            } catch (DuplicateKeyException duplicate) {
                // After the duplicate attempt's transaction rolls back,
                // swallow only when the consumer marker has already committed.
                if (!alreadyProcessed(event.eventId())) {
                    throw duplicate;
                }
            }
        }

        private boolean alreadyProcessed(UUID eventId) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_events " +
                "WHERE consumer_name = ? AND event_id = ?",
                Integer.class,
                CONSUMER,
                eventId.toString()
            );
            return count != null && count > 0;
        }

        public long totalCents() {
            Long result = jdbc.queryForObject(
                "SELECT COALESCE(SUM(amount_cents), 0) " +
                "FROM revenue_entries",
                Long.class
            );
            return result == null ? 0L : result;
        }

        public int processedCount() {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_events " +
                "WHERE consumer_name = ?",
                Integer.class,
                CONSUMER
            );
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = context.getBean(EventArchive.class);
            var report = context.getBean(RevenueListener.class);
            var gate = context.getBean(FailureGate.class);

            OrderPaid e1 = new OrderPaid(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000001"),
                101L, 500L
            );
            OrderPaid e2 = new OrderPaid(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000002"),
                102L, 700L
            );
            OrderPaid e3 = new OrderPaid(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000003"),
                101L, 300L
            );

            archive.appendAndPublish(e1);
            archive.appendAndPublish(e2);

            System.out.println(
                "first: total=" + report.totalCents()
                + " processed=" + report.processedCount()
                + " archived=" + archive.archivedCount()
            );

            archive.replayAll();

            System.out.println(
                "replay: total=" + report.totalCents()
                + " processed=" + report.processedCount()
            );

            gate.failNextProcessing();

            try {
                archive.appendAndPublish(e3);
            } catch (IllegalStateException ex) {
                System.out.println("injected failure observed");
            }

            System.out.println(
                "failed: total=" + report.totalCents()
                + " processed=" + report.processedCount()
                + " archived=" + archive.archivedCount()
            );

            archive.replayAll();

            System.out.println(
                "retry: total=" + report.totalCents()
                + " processed=" + report.processedCount()
            );
        }
    }
}
~~~

### 6.5. Running and Checking Stdout

Install JDK 17+ and a compatible Gradle version, or use the project's Gradle Wrapper:

~~~bash
gradle run --quiet
# With Wrapper: ./gradlew run --quiet
# On Windows: gradlew.bat run --quiet
~~~

Lines printed explicitly by `main`, excluding dependency logs:

~~~text
first: total=1200 processed=2 archived=2
replay: total=1200 processed=2
injected failure observed
failed: total=1200 processed=2 archived=3
retry: total=1500 processed=3
~~~

**Explanation:**

1. E1 and E2 are two distinct events, archived and processed; total = 500 + 700 = 1,200.
2. Replay reads E1/E2 again with the **same `eventId`**. When inserting into `processed_events`, the unique constraint rejects the duplicate; the attempt's transaction rolls back, and the listener checks the already-committed marker and skips. Total remains 1,200.
3. E3 is archived successfully before publishing. `FailureGate` throws an exception after the listener has inserted into both the marker and projection tables, before the transaction commits.
4. E3's transaction rolls back both tables, so after the error **total is still 1,200**, **processed is still 2**, and **archived is 3**.
5. Calling `replayAll()`: E1/E2 are skipped, while E3 has no marker and gets processed; total = 1,500 and processed = 3.

There is no magic "automatic retry on failure." The demo code **explicitly calls** `replayAll()`. In production, a worker/outbox/broker scheduler handles redelivery, controlling backoff, ACKs, poison messages, and retry budgets.

**Significance of in-memory H2:** this properly tests transactions and unique constraints inside **one live JVM**. Because the database URL starts with `jdbc:h2:mem:`, it **does not preserve the archive across restarts**. Production data must live in a durable DB/broker if replay across process crashes is required.

## 7. JUnit 5: Testing Retries, Duplicates, and Failure Atomicity

Create `src/test/java/demo/ReplayableListenerDemoTest.java`:

~~~java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReplayableListenerDemoTest {

    private static ReplayableListenerDemo.OrderPaid paid(
            String suffix, long orderId, long cents) {

        return new ReplayableListenerDemo.OrderPaid(
            UUID.fromString(
                "00000000-0000-0000-0000-" + suffix),
            orderId,
            cents
        );
    }

    @Test
    void sameEventReplayDoesNotMultiplyRevenue() {
        try (var ctx = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = ctx.getBean(
                ReplayableListenerDemo.EventArchive.class);
            var report = ctx.getBean(
                ReplayableListenerDemo.RevenueListener.class);

            archive.appendAndPublish(
                paid("000000000001", 101L, 500L));
            archive.replayAll();
            archive.replayAll();

            assertEquals(500L, report.totalCents());
            assertEquals(1, report.processedCount());
            assertEquals(1, archive.archivedCount());
        }
    }

    @Test
    void failingAttemptRollsBackMarkerAndSideEffect() {
        try (var ctx = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = ctx.getBean(
                ReplayableListenerDemo.EventArchive.class);
            var report = ctx.getBean(
                ReplayableListenerDemo.RevenueListener.class);
            var gate = ctx.getBean(
                ReplayableListenerDemo.FailureGate.class);

            gate.failNextProcessing();

            assertThrows(
                IllegalStateException.class,
                () -> archive.appendAndPublish(
                    paid("000000000002", 102L, 700L))
            );

            assertEquals(0L, report.totalCents());
            assertEquals(0, report.processedCount());
            assertEquals(1, archive.archivedCount());

            archive.replayAll();

            assertEquals(700L, report.totalCents());
            assertEquals(1, report.processedCount());
        }
    }

    @Test
    void distinctEventIdsForSameOrderAreBothApplied() {
        try (var ctx = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = ctx.getBean(
                ReplayableListenerDemo.EventArchive.class);
            var report = ctx.getBean(
                ReplayableListenerDemo.RevenueListener.class);

            archive.appendAndPublish(
                paid("000000000003", 101L, 400L));
            archive.appendAndPublish(
                paid("000000000004", 101L, 200L));

            archive.replayAll();

            assertEquals(600L, report.totalCents());
            assertEquals(2, report.processedCount());
        }
    }
}
~~~

Run:

~~~bash
gradle test
# Linux/macOS Wrapper: ./gradlew test
# Windows Wrapper: gradlew.bat test
~~~

Expect **3 passing tests** with the example's configuration:

- **Replay one event** multiple times without increasing `totalCents` or marker count.
- **Mid-transaction failure:** both side effect and marker roll back together, allowing replay to re-run afterward.
- **Two distinct event IDs for the same order:** counted separately, not wrongly dropped just because `orderId` matches.

Each test creates an `ApplicationContext` with a randomized H2 database name to avoid cross-test data leakage. No `Thread.sleep()` is needed; the demo uses a synchronous listener, so results are readable immediately after each successful `publishEvent`.

Note: this test suite does not prove full handling of multi-threaded races, process crashes, broker partitions/rebalances, or external side effects. Those scenarios require integration/failure-injection tests against corresponding production infrastructure.

## 8. Key Takeaways on Transactions, Exceptions, and Concurrency

### 8.1. Why Must the Marker and Effect Share One Transaction?

A listener like this is **unsafe**:

~~~java
// Illustrative anti-pattern, not a standalone program.
if (!seen(event.eventId())) {
    projection.increment(event.amountCents());
    markProcessed(event.eventId());
}
~~~

If `increment` commits before `markProcessed` and the process dies, a retry increments again. If `markProcessed` commits before `increment` and the process dies, the event is marked done while the projection was never updated.

Use the same transaction and a **unique key in the database**. The unique constraint protects against two concurrent workers both seeing "not yet processed."

### 8.2. SELECT-Before-INSERT Has a Race Condition

~~~text
Worker A: SELECT marker E1 => absent
Worker B: SELECT marker E1 => absent
Worker A: process
Worker B: process
~~~

You cannot rely on `if (not exists)` in application code to prevent duplicates. You need a database unique constraint or atomic claim/locking depending on the DB; competing workers must handle conflicts properly.

In the demo, the worker **inserts the marker first** with primary key `(consumer_name, event_id)`. On duplicate, the error is caught **outside the transaction** and the code verifies the marker has already committed. With other DBs/drivers, duplicate errors may surface via SQL/vendor-specific codes; do not catch every `DataAccessException` and treat it as a duplicate. If a transaction fails due to deadlock/timeout, retry according to a separate policy.

### 8.3. Why Not Swallow Every Exception?

~~~java
// Wrong: turns an infrastructure error into "processed."
try {
    process(event);
} catch (Exception ignored) {
    return;
}
~~~

If a listener reports success when the DB is temporarily unreachable, a broker may ACK and permanently stop redelivering the event. Skip only **confirmed duplicates**, never errors of unknown outcome. Emit error logs/metrics keyed by `eventId` and `consumer`; use retries with backoff, timeouts, and DLQs where appropriate.

### 8.4. What Does REQUIRES_NEW Solve?

The demo configures `TransactionTemplate` with `PROPAGATION_REQUIRES_NEW` so the consumer gets its own local transaction rather than joining the caller's transaction. This is a choice **for the example**, not mandatory for every listener.

If business rules require audit/projection updates to roll back **together with** the main use case, sharing one transaction may be right. If a handler runs `AFTER_COMMIT` or outside a transaction, it may need a new transaction to write to the DB.

**Do not use `REQUIRES_NEW` out of habit:** it can commit side effects independently even when the caller's transaction subsequently rolls back. Define clearly when the source event counts as a committed fact.

## 9. Safe Replay Rebuilds State Without Re-Triggering Every Side Effect

A major hazard when replaying through a shared event bus: if historical events are re-published to **all listeners**, side effects that must not repeat can be triggered again.

~~~text
Replay OrderPaid E1
    +--> RevenueProjection: should rebuild
    +--> AuditProjection  : may rebuild
    +--> EmailSender      : DO NOT resend emails needlessly
    +--> PaymentGateway   : DO NOT charge again
    +--> Analytics        : may recompute in a controlled manner
~~~

Distinguish clearly:

- **Projection listeners:** turn events into derived state (reporting, search indexes), rebuildable with the right schema/version/ordering.
- **Effect listeners:** call external systems (email, push, payments), requiring explicit side-effect policies and destination idempotency; do not auto-run during a data rebuild.
- **Audits:** may need to preserve historical audit trails rather than deleting and re-emitting as new side effects.

When building production replay, use a **replay runner that targets only authorized projection consumers**, or a separate stream/topology. Do not blast full history back onto a topic/event bus shared with effect listeners without guard checks. Never use an `isReplay` flag inside the payload as the sole safeguard when consumers hold high-impact privileges; design proper authorization and pipelines.

### Side Effects Outside the Database

When calling a payment provider or email gateway:

~~~text
Consumer receives E1
  -> remote API accepts request
  -> consumer crashes before recording DONE
  -> E1 redelivered
~~~

The local marker was not saved, so the second attempt can still call the API. You need a **stable idempotency key** supported by the destination, or a dedup/reconciliation protocol analyzing ambiguous timeout cases. You cannot span an atomic transaction across every database, HTTP API, and broker with `@Transactional` alone.

## 10. Transactional Outbox and a Durable Replay Source

The demo's `EventArchive.appendAndPublish` simply writes the event to a separate table before publishing. Production requires consistency between domain state and the replay source.

A common architecture:

~~~text
BEGIN T1
    UPDATE orders SET status='PAID' WHERE id=101
    INSERT INTO outbox(
        event_id, event_type, aggregate_id,
        schema_version, payload, occurred_at
    ) VALUES (...)
COMMIT T1
          |
          v
Outbox relay / broker
          |
          +--> consumer retry/replay by stable eventId
                    |
                    +--> inbox marker + projection update
                    |    in one local transaction
                    |
                    +--> ACK after commit
~~~

By writing **domain state and the outbox record in the same transaction**, the event is durably saved if and only if the domain change commits. Events dispatched later by a worker can still repeat: the outbox solves losing work, while the **idempotent consumer** solves duplicate delivery.

**Distinguish an outbox from an event store:**

- An outbox typically serves message delivery with bounded retention; sent rows can be pruned.
- An event store retains history long enough and with enough data for full replay/rebuilds as required.
- Once `DONE` outbox rows are deleted, you cannot expect to replay **complete history** from that outbox.
- An event table holding only `orderId` without needed historical data may be insufficient to reconstruct projections accurately.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` binds handlers to the commit phase, yet **does not create durable storage by itself**. Crashing after commit before enqueuing can still lose tasks. Calling the listener outside a transaction skips the transaction-bound callback by default because `fallbackExecution=false`.

Reactive transactions use Reactor Context and `TransactionalEventPublisher` when appropriate; do not assume servlet thread-local transactions apply to reactive listeners.

## 11. Replay and Rebuild: Managing Versions and Checkpoints

When rebuilding a projection from history, you should not necessarily reuse old production markers. If consumer v1 already processed E1, a v2 rebuild still needs to apply E1 into the **new projection**.

Two common strategies:

1. **Per-projection versioning:** key processed markers by `(consumer_name, projection_version, event_id)` or a separate namespace.
2. **Shadow projection + atomic cutover:** build `revenue_projection_v2` from event history, verify totals/reconcile, and switch the application to read v2; never drop v1 while production is still reading it.

~~~text
Event store E1..En
       |
       +--> Consumer report-v1 -> projection_v1 (live serving)
       |
       +--> Consumer report-v2 -> projection_v2 (rebuilding)
                                      |
                                verify/checkpoint
                                      |
                                 atomic switch
~~~

**Checkpoints/offsets do not replace event-level idempotency.** A crash can occur after writing part of a batch before updating the checkpoint; replaying that batch must remain safe. Checkpoints should be updated alongside projection state in an appropriate transaction, or paired with explicit at-least-once + deduplication semantics.

If the system keeps receiving live events during a rebuild, provide a way to **catch up** the tail from the snapshot/offset without dropping or double-counting events. At cutover time, verify the new projection has reached the required consistency level.

### Schema Evolution and Historical Data

Events from three years ago may follow schema v1 while new consumers expect schema v3. You need:

- explicit `eventType` and `schemaVersion`;
- upcasters/adapters tested against every stored version;
- default rules for new fields without fabricating nonexistent historical facts;
- quarantine/DLQ and alerts for unsupported events instead of silently dropping them;
- ability to dry-run replays in a staging environment before production.

If a replaying consumer queries **current state** by `orderId` instead of using historical facts, results may differ from the original point in time. That may be acceptable when rebuilding a current-state projection, but wrong for other goals (such as historical daily reports). Define your source of truth and projection semantics explicitly.

## 12. Ordering, Concurrency, and Reprocessing

When events represent non-commutative deltas, order matters:

~~~text
E1: account status = ACTIVE, version=4
E2: account status = SUSPENDED, version=5
~~~

If E2 is applied first and E1 arrives late, a blind overwrite could revert the status back to `ACTIVE`. Listeners must guard with:

- aggregate version/sequence, applying only valid transitions;
- partitioning by `aggregateId` to preserve order within required scope;
- concurrency control / optimistic locking;
- pausing and fetching missing events on gaps instead of guessing values.

Never confuse `occurredAt`/timestamps with absolute sequence numbers: clock skew and identical timestamp resolution can misorder events. Never claim that a local queue's FIFO guarantees ordering across multiple workers, partitions, or instances.

For summing revenue from independent payments, addition is value-commutative, yet **duplicates still corrupt the total**, so deduplication is required. For versioned state transitions, **both deduplication and ordering** must be designed.

## 13. Observability for Replayable Listeners

Metrics must distinguish:

| Suggested Metric | Meaning |
| --- | --- |
| `event.deliveries.total` | Times a consumer received/was invoked, including duplicates |
| `event.applied.total` | New events successfully applied |
| `event.duplicates.skipped.total` | Duplicate deliveries intentionally skipped |
| `event.processing.errors.total` | Failed attempts, categorized by cause |
| `event.retry.total` | Number of retries |
| `event.replay.run.total` | Number of replay job executions |
| `event.replay.lag` | Replay/catch-up lag by offset or event age |
| `event.inbox.pending` | Unfinished items in inbox/queue |
| `event.projection.drift` | Discrepancies vs. source data found during reconciliation |

These names are **application-defined**; Spring does not create all of these metrics automatically.

Log at minimum `eventType`, `eventId`, `consumer`, `attempt`, `outcome`, `duration`, replay vs. normal mode, and an appropriate correlation ID. Never put `eventId` or `correlationId` into metric tags: cardinality grows unboundedly with every event. Never log raw credentials or unnecessary PII in event payloads or DLQs.

A replay campaign should carry a **run ID** for auditing and dashboard progress tracking, though the run ID does not replace the original occurrence's `eventId`.

## 14. Failure Scenarios and Proper Expectations

| Scenario | Expected Outcome |
| --- | --- |
| E1 delivered once | Projection applies E1, marker commits |
| E1 redelivered after success | No additional effect applied |
| Failure before marker/effect commit | Transaction rolls back; retry can reprocess cleanly |
| Crash after commit before ACK | Redelivery sees marker, skips, and ACKs |
| Workers A and B process E1 concurrently | Unique constraint/atomic claim prevents double-apply |
| Two different event IDs for same order | Both processed separately if distinct valid facts |
| DB timeout/deadlock error | Not mistaken for duplicate; bounded retry/backoff |
| Remote side effect occurred, local ACK lost | Destination idempotency key or reconciliation handles it |
| Rebuild v2 from history | Uses v2 projection/marker namespace; not skipped by v1 markers |
| Replay missing historical records | Cannot reconstruct accurately from an incomplete source |
| Unsupported old event schema | Upcast or quarantine with audit; never silently drop |
| Out-of-order event arrival | Version/sequence check or gap-handling mechanism |
| Permanently failing consumer (poison event) | Retry budget, DLQ, alerts, and controlled reprocessing tools |

### No Free "Exactly-Once"

A local transaction combining a unique marker + projection can make a **database effect** effectively-once within a narrow boundary. That does not mean external API calls, emails, push notifications, and broker commits are all simultaneously exactly-once.

The practical contract is usually **at-least-once delivery + idempotent processing**. More important than the "exactly-once" label is specifying concretely: one event, one consumer, one side effect, one transaction, and how timeouts/retries are handled.

## 15. Common Mistakes

**Mistake 1 — Assuming `@EventListener` replays automatically after restart.** Default Spring application events only dispatch; replay requires an archive, event store, or broker.

**Mistake 2 — Using `orderId` as the sole deduplication key.** One order can emit multiple distinct events; keep `eventId` per fact.

**Mistake 3 — Regenerating UUIDs on retry.** Doing so turns a duplicate delivery into an apparently brand-new event.

**Mistake 4 — Saving marker and side effect in two transactions.** Crashes cause false skips or double-applies.

**Mistake 5 — Checking only `SELECT NOT EXISTS` before `INSERT`.** Two concurrent workers can both see no marker; use a unique key or atomic claim.

**Mistake 6 — Catching every `Exception` and ACKing success.** DB or external API failures must not be disguised as duplicates.

**Mistake 7 — Replaying onto the whole bus, accidentally resending emails or recharging cards.** Projection rebuilds need a dedicated path respecting side-effect policies.

**Mistake 8 — Using `@Async` as a retry engine.** Async only switches threads; it provides no durable log, retries, or ACKs by default.

**Mistake 9 — Treating `@TransactionalEventListener(AFTER_COMMIT)` as durable.** Post-commit callbacks have a crash window; use an outbox when events must not be lost.

**Mistake 10 — Deleting the projection and replaying with old markers.** Old markers still claim every event was processed; rebuilds must use a new version/namespace.

**Mistake 11 — Rebuilding from current state for all historical reports.** Current state may have mutated or lack historical details. Define immutable facts and schema evolution.

**Mistake 12 — Testing only the happy path and a single sequential duplicate.** Production requires testing concurrency, timeouts, crashes, poison events, old schemas, and cutovers.

**Mistake 13 — Failing to restrict replay permissions.** Replay can trigger massive workloads; enforce IAM, auditing, rate limits, and isolation from side-effect consumers.

**Mistake 14 — Putting raw secrets in event payloads.** Stored and replayed events widen exposure; include only necessary metadata with proper ACLs.

## 16. Replayable Listener Design Checklist

- [ ] Events have a stable `eventId`, immutable payload, and explicit version.
- [ ] Retry, redelivery, replay, and rebuild are clearly defined for the use case.
- [ ] A replay source exists with appropriate durability, retention, completeness, and ordering.
- [ ] Deduplication keys are scoped by **consumer + `eventId`** or an equivalent idempotent model.
- [ ] Marker and local effect commit atomically in the same transaction.
- [ ] Unique constraints or atomic claims prevent concurrent duplicates.
- [ ] Already-processed duplicates are distinguished from DB errors or payload mismatches.
- [ ] Ambiguous timeouts and external side effects use stable idempotency keys.
- [ ] Rebuilding projections does not re-send emails or re-trigger payments.
- [ ] Reprocessing uses version/namespace isolation and shadow projection cutovers.
- [ ] Schema evolution/upcasting is tracked and incompatible old events are handled safely.
- [ ] Live-event catch-up and controlled cutover are planned.
- [ ] Tested failure injection before commit, retry after rollback, and crash after commit before ACK.
- [ ] Tested concurrency, out-of-order events, poison events, and retry budgets before rollout.
- [ ] Metrics/logs expose deliveries, applied counts, duplicates, errors, and replay lag.
- [ ] Replay operations are authorized, audited, and rate/scope-limited.
- [ ] Payloads contain no secrets, unnecessary personal data, or unsafe HTTP/JPA lifecycle objects.

### Key Takeaway

~~~text
publishEvent() = dispatch, NO automatic event history.

To replay:
    have a durable event history source with sufficient data.

To prevent double-apply:
    stable eventId
    + consumer-specific dedup
    + unique constraint
    + marker and local effect in the same transaction.

To rebuild projections:
    use a separate consumer/projection version,
    never replay dangerous side effects.

To survive crashes:
    durable outbox/broker + ACK/retry/idempotency.

Safe replayability is not "zero exceptions."
Safe replayability is producing the right result even when events are delivered multiple times.
~~~

## References

- [Spring Framework 6.2 — ApplicationContext Events, `@EventListener`, and `@Async`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — `TransactionTemplate` and Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Microsoft Azure Architecture Center — Idempotent Consumer Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer)
