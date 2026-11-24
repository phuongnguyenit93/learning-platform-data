# Duplicate Messages, Idempotency, and Business Side Effects

## 1. A message processed twice can cause real damage

In the **Spring Boot - testing** module, **Messaging** group, a consumer receiving the same message multiple times is a **normal scenario that must be designed and tested**, not necessarily a broker bug.

For example, a service receives a wallet credit event:

~~~json
{
  "eventId": "10000000-0000-4000-8000-000000000001",
  "accountId": "wallet-7",
  "deltaCents": 250
}
~~~

If the consumer runs `UPDATE wallets SET balance_cents = balance_cents + 250` **every time it receives a delivery**, a redelivered message can raise the balance by **500 cents** instead of **250 cents**. In other domains, the damage could be sending two emails, deducting inventory twice, creating two orders, double-charging a payment gateway, or granting entitlements multiple times.

There are three separate questions:

1. **Message delivery:** when can the broker redeliver a message, and what do offsets/acks actually confirm?
2. **Idempotency:** does processing the same **logical event** multiple times guarantee the business effect happens only once?
3. **Business side effects:** are there effects outside the database transaction — emails, payment APIs, Kafka publishes, files, caches — that a simple deduplication table **cannot protect on its own**?

This lesson implements an **at-least-once delivery + idempotent consumer** model along with direct and embedded-Kafka testing strategies; testing duplicates, two legitimate events with identical amounts/accounts but distinct IDs, conflicting payloads, marker rollback on failure, concurrency, retry/DLT, ordering, and transactional outboxes.

The main example uses **Java 17, Spring Boot 3.5.16, Spring Kafka 3.3.x per BOM, Spring JDBC, H2, JUnit Jupiter**, and `spring-kafka-test`. One test class exercises the handler/DB directly and another uses **`@EmbeddedKafka`** to send two real Kafka records with the same `eventId`. H2 suffices to demonstrate transactions and unique keys; testing production-like contention/locking should use PostgreSQL/MySQL Testcontainers matching the real DB.

## 2. Distinguishing duplicate messages from two legitimate actions

A "duplicate message" must be defined by the **stable identity of a logical event**, not merely by comparing JSON bodies or account IDs.

| Case | Same `eventId`? | Content? | Proper handling |
| --- | --- | --- | --- |
| Broker redelivers record after crash/ack failure | Yes | Same payload | **Do not apply business effect again** |
| Producer retries and publishes duplicate logical event | Yes if producer preserves ID across retries | Same payload | Skip already-committed effect |
| User makes two legitimate top-ups | **Different** `eventId` | May have same account and amount | **Apply both** |
| Same `eventId` yet different amount/account | Yes | **Conflicting** | Raise conflict, do not silently skip |
| Two different consumer projections consume same event | Yes | Same payload | Each consumer processes within **its own projection scope** |
| Historical replay after schema migration | Yes | May differ in event version | Needs dedicated replay/deduplication policy |
| One event contains multiple items | Yes | One logical command with multiple effects | Must be atomic/idempotent for the whole business unit |

A helpful equation:

\[
f(f(S,e),e)=f(S,e)
\]

Where `S` is the business state and `e` is the logical event. Idempotent processing means applying the same event again **does not change the business outcome**, within the defined retention window and system scope. It **does not** mean two distinct events that happen to share identical content get merged.

**Pick the right key:** an `eventId` or `idempotencyKey` assigned by the producer **once per logical action** and resent verbatim on retries. Kafka's `topic-partition-offset` identifies a record in a log, yet **is not always the logical-event key**: a producer may republish the same event at a new offset. Correlation IDs/request tracing IDs should also not default to idempotency keys.

With multi-tenancy or multiple independent consumers, the key usually needs scoping:

~~~text
(consumer_name, tenant_id, event_id)
~~~

If producer IDs are unstable or clients omit keys, design an explicit business key (`orderId` + transition/version, payment provider idempotency key) and conflict analysis rather than hashing raw JSON and declaring it safe.

## 3. Why do brokers redeliver messages?

A realistic scenario:

~~~text
Kafka broker             Consumer                  Database
    |                        |                         |
    |---- event E ---------->|                         |
    |                        |--- BEGIN -------------->|
    |                        |--- UPDATE + marker ----->|
    |                        |--- COMMIT -------------->|
    |                        |
    |     JVM crashes before Kafka offset is committed
    |                        |
    |---- redeliver E ------>|                         |
    |                        |--- sees marker E ------->|
    |                        |--- NO second update ---->|
    |                        |--- returns success -----|
    |<--- offset commit -----|                         |
~~~

When the consumer commits the database **before** committing the Kafka offset, there is a window where the business effect has committed yet Kafka can still redeliver. If the Kafka offset is committed **before** the database and the process dies, the business effect can be lost. You cannot solve this trade-off merely by promising "the consumer will receive it once".

Sources of duplicates include:

- Consumer crash/restart after DB commit yet before ack/offset commit.
- Retries when a network timeout leaves the caller **unsure** whether the prior attempt finished.
- Consumer group rebalances with uncommitted offsets.
- Producer retries or event replays landing at new offsets.
- DLQ/DLT replays, incident recovery, or backfills.
- Manual reprocessing from an older timestamp/offset.
- Parallel workers receiving copies from retry topics or another integration path.

Important differences between Kafka and RabbitMQ:

- **Kafka:** consumers track/commit offsets; records stay in the log per retention. Offsets can be re-read on consumer restart, seek, rebalance, or replay.
- **RabbitMQ:** consumers ack deliveries; if a channel/connection closes before ack, unacked messages can normally be requeued/redelivered; nack/reject/DLX settings affect routing.
- **SQS/visibility-timeout queues:** messages reappear when the visibility timeout expires before the worker deletes them.

Never conclude that because a broker "has exactly-once", side effects in external databases or APIs are also exactly-once.

## 4. Delivery semantics, producer idempotence, and Kafka transactions

| Mechanism | Typical guarantee scope | What the app still needs |
| --- | --- | --- |
| At-most-once | Avoids redelivery by recording/acking before processing | Can **lose** effects if crash happens after ack |
| At-least-once | Retries/redelivers when unconfirmed | Consumer idempotence and cleanup |
| Kafka idempotent producer | Prevents certain duplicates **from producer retries within a producer session/partition** | Deduplicating logical events from separate publishes/replays |
| Kafka transactions/EOS | Atomically commits Kafka output records + consumer offsets within compatible Kafka topologies | Does not automatically make DB/email/payment atomic with Kafka |
| DB unique constraint | Only one transaction can insert the marker for a scoped event key | Transaction must enclose **both marker and business mutation** |
| Provider API idempotency key | Prevents duplicate effects at provider API if provider guarantees it | Keep key stable and honor retention/timeout contracts |

Kafka transactions are useful for **consume-transform-produce** within Kafka and `read_committed` consumers, yet **a Kafka transaction is not an automatic distributed transaction with a database or payment gateway**. Spring Kafka offers transaction synchronization between JDBC and Kafka, though one side can still commit while the other fails; compensation/outbox/idempotence are still needed depending on goals.  

Therefore, the safe mindset is: **delivery can repeat; business effects must guard against repetition**. This applies even when "exactly-once" is a product requirement: define "exactly once" **at which business boundary**, rather than stopping at broker config.

## 5. Mistake: SELECT then UPDATE without a unique constraint

A fragile implementation:

~~~java
// ANTI-EXAMPLE - race condition if two consumers process E together.
if (!wasProcessed(event.eventId())) {
    addBalance(event.accountId(), event.deltaCents());
    markProcessed(event.eventId());
}
~~~

Two workers can both observe `wasProcessed=false` before either writes the marker:

~~~text
Worker A: SELECT E -> not found
Worker B: SELECT E -> not found
Worker A: UPDATE balance +250
Worker B: UPDATE balance +250
Worker A: INSERT processed E
Worker B: INSERT processed E
~~~

Without a unique constraint, both succeed. With a unique constraint where the marker is written **after** the balance update, both statements must share the same database transaction; without a transaction, the balance is already credited before the marker insert fails.

**Core principles:**

1. Create a DB unique key such as `PRIMARY KEY(consumer_name, event_id)`.
2. **Within the same transaction**, insert the marker first and then apply the business state change.
3. If the marker is a duplicate, the transaction must not execute the business effect.
4. Catch `DuplicateKeyException` **outside** the transactional proxy so the failed transaction has rolled back completely; then query the committed marker and compare payloads to decide between "valid duplicate" and "event ID collision".
5. Return listener success/ack only after the transaction commits or the safe duplicate is confirmed.

In PostgreSQL, an INSERT violating a unique constraint puts the current transaction into an aborted state; catching the exception **inside the same transaction and issuing further SQL** is wrong. The main example lets the exception cross the `@Transactional` service proxy before the listener classifies the duplicate.

## 6. Putting the inbox marker in the same transaction as the business mutation

A safer flow:

~~~text
Consumer receives event E
       |
       v
BEGIN database transaction
       |
       v
INSERT inbox(consumer, event_id, account_id, delta)
       |
       +-- success ----------> UPDATE balance
       |                            |
       |                            +-- success -> COMMIT
       |                            +-- failure -> ROLLBACK marker + UPDATE
       |
       +-- duplicate key ---> ROLLBACK new transaction
                                    |
                                    v
                           Query committed marker
                                    |
                          same payload?  YES -> success/no-op
                                         NO  -> conflict/error
~~~

If the business row `UPDATE` fails (missing account, check constraint, deadlock, timeout), the entire transaction rolls back including **the marker**. Thus a retry after fixing the cause can process the event instead of skipping it as "already processed" prematurely.

If the marker commits while the business effect runs in **another transaction**, atomicity breaks. This is a common bug when the marker service uses `REQUIRES_NEW` while the business service uses `REQUIRED`: the marker survives the business rollback, causing all retries to be skipped. Never use `REQUIRES_NEW` for the marker when **marker and business update must commit/roll back together**.

**A transaction covers only resources managed by that transaction manager.** Emails, HTTP payment calls, and broker publishes do not automatically roll back when a JDBC transaction rolls back.

## 7. Minimal runnable example

We use a "credit event" representing adding **cents** to a wallet balance using `long` integers, avoiding `double`/`float` for money. The application has a Kafka listener consuming JSON; the business effect updates `credit_accounts.balance_cents` and inserts a marker into `credit_inbox`.

Design:

- Each credit event has `UUID eventId`, `String accountId`, `long deltaCents`.
- `CreditProcessor.apply(...)` is a `@Transactional` Spring service that writes the marker and credits the balance.
- `CreditKafkaListener.onMessage(String json)` parses JSON, calls the processor **through the Spring proxy**, catches `DuplicateKeyException` **after transaction rollback**, checks the prior payload, and no-ops on valid duplicates.
- `DeliveryObserved` is an **example observation event**, published after handling completes so the Kafka test can wait for both deliveries; it is not a production delivery/event guarantee.
- Two test types: direct listener + H2 for fast DB idempotency tests, and an embedded Kafka test for broker → consumer → DB.

Directory structure:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/credit/
  CreditApplication.java
  CreditEvent.java
  CreditProcessor.java
  DeliveryObserved.java
  CreditKafkaListener.java
src/main/resources/
  application.properties
src/test/resources/
  application.properties
  schema.sql
src/test/java/com/example/credit/
  CreditListenerDatabaseTest.java
  CreditEmbeddedKafkaTest.java
~~~

Every Java file is in package `com.example.credit`. No Docker is needed for this **embedded Kafka + H2** example; however, it is an integration test with an in-process broker and does not prove multi-broker/auth/TLS production Kafka setups.

## 8. Build: Java 17 / Spring Boot 3.5.16

**`settings.gradle`:**

~~~groovy
rootProject.name = 'credit-idempotency-tests'
~~~

**`build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

- Spring JDBC handles DB transactions and `JdbcTemplate`.
- Starter JSON provides Jackson `ObjectMapper` for JSON records.
- `spring-kafka` provides `@KafkaListener`/`KafkaTemplate`.
- `spring-kafka-test` provides `@EmbeddedKafka`.
- H2 keeps tests fast and standalone; production must use a real JDBC driver and database.
- Spring Boot BOM manages Spring Kafka/Apache Kafka client/Jackson versions; never manually pin a different Kafka major version without verifying compatibility.

`maxParallelForks=1` only limits concurrent Gradle test worker JVMs **within this task**; it does not automatically disable JUnit parallelism, multi-module jobs, or CI shards.

**`src/main/resources/application.properties`:**

~~~properties
app.kafka.credit-topic=credit-events
spring.kafka.consumer.group-id=credit-balance-consumer
~~~

Production needs `spring.kafka.bootstrap-servers`, serializers/deserializers, security, and datasource settings per environment. The file above holds no credentials.

## 9. Test schema and properties for standalone execution

**`src/test/resources/schema.sql`:**

~~~sql
CREATE TABLE IF NOT EXISTS credit_accounts (
    account_id VARCHAR(80) PRIMARY KEY,
    balance_cents BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_inbox (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    account_id VARCHAR(80) NOT NULL,
    delta_cents BIGINT NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

`PRIMARY KEY(consumer_name,event_id)` is the **final concurrency barrier**: two transactions cannot both commit a marker for the same scoped logical event, even if both initially saw no row.

**`src/test/resources/application.properties`:**

~~~properties
spring.datasource.url=jdbc:h2:mem:credit_idempotency;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=6
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql

spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.listener.auto-startup=false
~~~

By default, the test app sets `listener.auto-startup=false` so **direct tests** do not try connecting to `localhost:9092`. `CreditEmbeddedKafkaTest` overrides it to `true` and supplies `spring.kafka.bootstrap-servers` from the embedded broker.

`DB_CLOSE_DELAY=-1` keeps H2 alive within the JVM, so fixtures need explicit cleanup, especially across multiple Spring contexts. This is not a production database. When switching from H2 to PostgreSQL, use real application migrations and test contention/SQL dialects against PostgreSQL.

## 10. Spring Boot app and event schema

**`src/main/java/com/example/credit/CreditApplication.java`:**

~~~java
package com.example.credit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CreditApplication {
    public static void main(String[] args) {
        SpringApplication.run(CreditApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/credit/CreditEvent.java`:**

~~~java
package com.example.credit;

import java.util.UUID;

public record CreditEvent(
        UUID eventId,
        String accountId,
        long deltaCents
) {
}
~~~

JSON uses a UUID string and integer `deltaCents`. Some systems use `BigDecimal` with currency codes/scales; the example chooses cents to avoid floating-point confusion. Production should validate amount bounds, currency, tenant, schema version, source signatures, authorization, overflow, and balance rules per contract.

### Do not use JSON content as the sole identity

Two valid transactions can have **identical** account/amount payloads while representing two separate payments. Conversely, the same logical event might serialize with different JSON field ordering while keeping the same ID. Therefore `eventId` must remain stable across retries, and payloads are stored/compared by the **canonical business fields** of the event version.

## 11. `CreditProcessor`: marker and atomic balance update

**`src/main/java/com/example/credit/CreditProcessor.java`:**

~~~java
package com.example.credit;

import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreditProcessor {
    private static final String CONSUMER = "credit-balance-v1";

    private final JdbcTemplate jdbc;

    public CreditProcessor(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Transactional
    public void apply(CreditEvent event) {
        Objects.requireNonNull(event, "event");

        if (event.eventId() == null
                || event.accountId() == null
                || event.accountId().isBlank()
                || event.deltaCents() <= 0) {
            throw new IllegalArgumentException("Invalid credit event");
        }

        // Primary key blocks duplicates before the business UPDATE.
        jdbc.update(
                """
                INSERT INTO credit_inbox
                  (consumer_name, event_id, account_id, delta_cents)
                VALUES (?, ?, ?, ?)
                """,
                CONSUMER,
                event.eventId().toString(),
                event.accountId(),
                event.deltaCents()
        );

        // Atomic SQL UPDATE; do not SELECT balance then overwrite it.
        int changed = jdbc.update(
                """
                UPDATE credit_accounts
                SET balance_cents = balance_cents + ?
                WHERE account_id = ?
                """,
                event.deltaCents(),
                event.accountId()
        );

        if (changed != 1) {
            throw new IllegalStateException(
                    "Unknown account: " + event.accountId()
            );
        }
    }

    // Called after the duplicate INSERT transaction has rolled back.
    public boolean matchesCommittedEvent(CreditEvent event) {
        List<Boolean> matches = jdbc.query(
                """
                SELECT account_id, delta_cents
                FROM credit_inbox
                WHERE consumer_name = ? AND event_id = ?
                """,
                (rs, rowNum) ->
                        event.accountId().equals(
                                rs.getString("account_id")
                        )
                        && event.deltaCents()
                                == rs.getLong("delta_cents"),
                CONSUMER,
                event.eventId().toString()
        );
        return matches.size() == 1 && matches.get(0);
    }
}
~~~

**Why is this design sound?**

1. `@Transactional` on a Spring service creates a DB transaction, and the listener calls it **through the proxy**.
2. The unique marker is INSERTed **before** the business UPDATE.
3. If the account does not exist, the service throws an unchecked `IllegalStateException`. Spring rolls back both the marker and all SQL executed in that transaction.
4. If `eventId` is a duplicate, the database rejects the INSERT before the balance is credited.
5. `matchesCommittedEvent` runs **after the failed transaction rolls back**, avoiding aborted-transaction SQL errors on duplicate keys and avoiding reading uncommitted temporary state.
6. If the same ID arrives with a different account/amount, the test must report a conflict rather than treating it as a safe duplicate.

**Do not do this:** catch `DuplicateKeyException` **inside** `apply` and keep issuing SQL on the same transaction. PostgreSQL marks a failed transaction as aborted. Other databases have different semantics, so keeping the catch outside the transactional proxy is the safer strategy.

### Business limitations

This is a cents-addition example without overflow protection, currency conversion, limits, authorization, or an immutable audit ledger. Production needs balance rules, account ownership, timeout/lock handling, and schema evolution. This marker protects the **DB balance effect** inside one database transaction; it does not by itself protect emails or payment APIs.

## 12. Listener: classifying `APPLIED`, `DUPLICATE`, and `CONFLICT`

**`src/main/java/com/example/credit/DeliveryObserved.java`:**

~~~java
package com.example.credit;

import java.util.UUID;

public record DeliveryObserved(
        UUID eventId,
        String outcome
) {
}
~~~

`DeliveryObserved` is a Spring application event for **example/test observation**. Publishing an in-JVM event is not a durable message broker; if the process crashes, the event can be lost. Never use this record to fake a transactional outbox in production.

**`src/main/java/com/example/credit/CreditKafkaListener.java`:**

~~~java
package com.example.credit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class CreditKafkaListener {
    private final CreditProcessor processor;
    private final ObjectMapper json;
    private final ApplicationEventPublisher events;

    public CreditKafkaListener(
            CreditProcessor processor,
            ObjectMapper json,
            ApplicationEventPublisher events
    ) {
        this.processor = processor;
        this.json = json;
        this.events = events;
    }

    @KafkaListener(topics = "${app.kafka.credit-topic}")
    public void onMessage(String payload) {
        CreditEvent event;
        try {
            event = json.readValue(payload, CreditEvent.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Invalid credit event JSON", ex
            );
        }

        try {
            processor.apply(event);
            events.publishEvent(
                    new DeliveryObserved(event.eventId(), "APPLIED")
            );
        } catch (DuplicateKeyException duplicate) {
            if (!processor.matchesCommittedEvent(event)) {
                throw new IllegalStateException(
                        "Conflicting eventId: " + event.eventId(),
                        duplicate
                );
            }
            // Success/no-op: this exact event was already processed.
            events.publishEvent(
                    new DeliveryObserved(event.eventId(), "DUPLICATE")
            );
        }
    }
}
~~~

### Why catch in the listener?

`processor.apply(event)` is a call from one bean to another `@Transactional` bean. When a duplicate INSERT throws `DuplicateKeyException`, the Spring transaction interceptor rolls back **before the exception leaves the proxy** and reaches the listener. The listener can then query the committed marker on a healthy connection/transaction.

If the query confirms **the same eventId + business payload fields**, the handler returns normally; the broker container can treat that delivery as successful per ack mode/offset policy. If the same event ID arrives with different content, the listener throws; the error should be classified/routed to a DLT or alerted on rather than retried infinitely like a transient network error.

On JSON schema/validation errors, the handler also throws. In production, **poison messages should not be retried infinitely**; configure appropriate error handlers, retryable classifications, DLTs, and observability.

### A small note on publishing `DeliveryObserved`

`events.publishEvent(...)` here is synchronous by default after `apply(...)` returns/commits. If you later attach `@Async` to the observation listener, tests relying on that signal must switch to an appropriate wait. If an observer throws after the business commit, Kafka can redeliver; the DB marker still protects the balance, though the observer callback is not itself exactly-once. In production, keep probes/metrics decoupled from transaction contracts so telemetry never turns a completed delivery into an unintended failure.

## 13. JUnit direct integration test: verifying business effects without a broker

This class runs a real Spring context and **real JDBC/H2**, yet **does not start the Kafka consumer thread**; it calls `onMessage` directly to test idempotency logic before adding broker timing. Do not put `@Transactional` on the test class, because a test-managed outer transaction blurs the `@Transactional` processor's commit boundary and can let a unique violation mark the outer transaction rollback-only.

**`src/test/java/com/example/credit/CreditListenerDatabaseTest.java`:**

~~~java
package com.example.credit;

import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(properties = {
        "spring.kafka.listener.auto-startup=false"
})
class CreditListenerDatabaseTest {

    @Autowired
    CreditKafkaListener listener;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ObjectMapper mapper;

    private String account;

    @BeforeEach
    void createAccount() {
        account = "acct-" + UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO credit_accounts
                  (account_id, balance_cents) VALUES (?, ?)
                """,
                account, 1_000L
        );
    }

    @AfterEach
    void removeOnlyThisTestsRows() {
        jdbc.update(
                """
                DELETE FROM credit_inbox
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
        jdbc.update(
                """
                DELETE FROM credit_accounts
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
    }

    private String payload(CreditEvent event)
            throws JsonProcessingException {
        return mapper.writeValueAsString(event);
    }

    private long balance(String accountId) {
        Long value = jdbc.queryForObject(
                """
                SELECT balance_cents FROM credit_accounts
                WHERE account_id = ?
                """,
                Long.class,
                accountId
        );
        return value.longValue();
    }

    private int markerCount(UUID eventId) {
        Integer found = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM credit_inbox
                WHERE consumer_name = ? AND event_id = ?
                """,
                Integer.class,
                "credit-balance-v1",
                eventId.toString()
        );
        return found.intValue();
    }

    @Test
    void sameEventTwiceChangesBalanceOnlyOnce() throws Exception {
        UUID id = UUID.randomUUID();
        String json = payload(new CreditEvent(id, account, 250L));

        listener.onMessage(json);
        listener.onMessage(json);

        assertThat(balance(account)).isEqualTo(1_250L);
        assertThat(markerCount(id)).isEqualTo(1);
    }

    @Test
    void twoDifferentEventIdsAreTwoLegitimateCredits()
            throws Exception {
        UUID first = UUID.randomUUID();
        UUID second = UUID.randomUUID();

        listener.onMessage(
                payload(new CreditEvent(first, account, 100L))
        );
        listener.onMessage(
                payload(new CreditEvent(second, account, 200L))
        );

        assertThat(balance(account)).isEqualTo(1_300L);
        assertThat(markerCount(first)).isEqualTo(1);
        assertThat(markerCount(second)).isEqualTo(1);
    }

    @Test
    void sameEventIdWithChangedAmountIsAConflict()
            throws Exception {
        UUID id = UUID.randomUUID();

        listener.onMessage(
                payload(new CreditEvent(id, account, 150L))
        );

        String conflicting = payload(
                new CreditEvent(id, account, 999L)
        );

        assertThatThrownBy(
                () -> listener.onMessage(conflicting)
        ).isInstanceOf(IllegalStateException.class)
         .hasMessageContaining("Conflicting eventId");

        assertThat(balance(account)).isEqualTo(1_150L);
        assertThat(markerCount(id)).isEqualTo(1);
    }

    @Test
    void failedBusinessUpdateRollsBackMarkerSoRetryCanWork()
            throws Exception {
        String missing = account + "-missing";
        UUID id = UUID.randomUUID();
        String json = payload(
                new CreditEvent(id, missing, 700L)
        );

        assertThatThrownBy(
                () -> listener.onMessage(json)
        ).isInstanceOf(IllegalStateException.class)
         .hasMessageContaining("Unknown account");

        assertThat(markerCount(id)).isZero();

        // Fix the temporary condition, then replay the SAME payload.
        jdbc.update(
                """
                INSERT INTO credit_accounts
                  (account_id, balance_cents) VALUES (?, ?)
                """,
                missing, 0L
        );

        listener.onMessage(json);

        assertThat(balance(missing)).isEqualTo(700L);
        assertThat(markerCount(id)).isEqualTo(1);
    }

    @Test
    void malformedJsonNeverChangesBusinessBalance() {
        assertThatThrownBy(
                () -> listener.onMessage("{not-json")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Invalid credit event JSON");

        assertThat(balance(account)).isEqualTo(1_000L);
    }

    @Test
    void nonPositiveDeltaIsRejectedBeforeMarker()
            throws Exception {
        UUID id = UUID.randomUUID();

        assertThatThrownBy(
                () -> listener.onMessage(
                        payload(new CreditEvent(id, account, 0L))
                )
        ).isInstanceOf(IllegalArgumentException.class);

        assertThat(balance(account)).isEqualTo(1_000L);
        assertThat(markerCount(id)).isZero();
    }
}
~~~

**Six test methods** exercise real JSON parsing, handler, and Spring JDBC transactions without depending on a Kafka broker. Observations:

- Duplicate with same ID/payload → balance rises by 250 only once, 1 marker.
- Two events with different IDs → both applied.
- Same ID with different amount → conflict, no second credit.
- Update to missing account → transaction rolls back marker; after creating the account, replaying the exact event succeeds.
- Malformed JSON → exception; balance unchanged.
- Invalid amount → neither marker nor effect written.

**QA note:** this test does not place `@Transactional` on the class. `@AfterEach` deletes only the test's own account IDs using a UUID namespace rather than wiping the whole table, reducing cross-suite interference. Never assert against hard-coded random UUIDs; only use the ID as a key to query the marker.

In production, `IllegalArgumentException` for invalid data does not automatically route to a DLT; configure appropriate listener error handling. This direct test **does not** prove Kafka offset/ack semantics.

## 14. Broker-level test: publish two Kafka records, await two deliveries

Use `@EmbeddedKafka` for a real in-JVM broker with a random port and `spring.kafka.bootstrap-servers` remapped properly. Calling `KafkaTemplate.send(...).get()` only guarantees the producer received the send result, **not that the consumer finished processing**. Therefore, the test uses `DeliveryObserved` and Awaitility to wait for both `"APPLIED"` and `"DUPLICATE"` outcomes **before asserting DB state**.

Spring Kafka 3.3 includes `@EmbeddedKafka` in `spring-kafka-test`; with Spring TestContext, the embedded broker belongs to the context. Docs recommend considering `@DirtiesContext` to avoid broker shutdown/context cache races after the test. 

**`src/test/java/com/example/credit/CreditEmbeddedKafkaTest.java`:**

~~~java
package com.example.credit;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(properties = {
        "app.kafka.credit-topic=credit-events-test",
        "spring.kafka.consumer.group-id=credit-embedded-test",
        "spring.kafka.listener.auto-startup=true"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "credit-events-test",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@Import(CreditEmbeddedKafkaTest.ProbeConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CreditEmbeddedKafkaTest {

    static class DeliveryProbe {
        private final Map<UUID, ConcurrentLinkedQueue<String>> observed =
                new ConcurrentHashMap<>();

        @EventListener
        public void onDelivery(DeliveryObserved event) {
            observed.computeIfAbsent(
                    event.eventId(),
                    ignored -> new ConcurrentLinkedQueue<>()
            ).add(event.outcome());
        }

        List<String> states(UUID id) {
            ConcurrentLinkedQueue<String> result = observed.get(id);
            return result == null ? List.of() : List.copyOf(result);
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ProbeConfig {
        @Bean
        DeliveryProbe deliveryProbe() {
            return new DeliveryProbe();
        }
    }

    @Autowired
    KafkaTemplate<String, String> kafka;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    DeliveryProbe probe;

    private String account;

    @BeforeEach
    void createIsolatedAccount() {
        account = "kafka-" + UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO credit_accounts
                  (account_id, balance_cents) VALUES (?, ?)
                """,
                account, 1_000L
        );
    }

    @AfterEach
    void removeOwnCommittedRows() {
        jdbc.update(
                "DELETE FROM credit_inbox WHERE account_id = ?",
                account
        );
        jdbc.update(
                "DELETE FROM credit_accounts WHERE account_id = ?",
                account
        );
    }

    private long balance() {
        Long result = jdbc.queryForObject(
                """
                SELECT balance_cents FROM credit_accounts
                WHERE account_id = ?
                """,
                Long.class,
                account
        );
        return result.longValue();
    }

    @Test
    void twoKafkaDeliveriesWithSameEventIdCreditOnlyOnce()
            throws Exception {
        UUID id = UUID.randomUUID();
        String payload = mapper.writeValueAsString(
                new CreditEvent(id, account, 250L)
        );

        // Use the same account key to preserve order within one partition.
        kafka.send(
                "credit-events-test", account, payload
        ).get(10, TimeUnit.SECONDS);
        kafka.send(
                "credit-events-test", account, payload
        ).get(10, TimeUnit.SECONDS);

        // Must observe both deliveries processed, not just
        // the balance after the first delivery.
        await().atMost(Duration.ofSeconds(20))
                .untilAsserted(() -> {
                    assertThat(probe.states(id))
                            .contains("APPLIED", "DUPLICATE");
                    assertThat(balance()).isEqualTo(1_250L);
                });

        Integer markers = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM credit_inbox
                WHERE consumer_name = ? AND event_id = ?
                """,
                Integer.class,
                "credit-balance-v1",
                id.toString()
        );
        assertThat(markers).isEqualTo(1);
    }
}
~~~

This test receives two Kafka **records** for the same logical event without simulating a real crash/rebalance. It verifies **Kafka listener wiring + JSON parsing + DB idempotency + observing both deliveries**.

**Do not claim** this tests a crash right at Kafka offset commit; that scenario requires fault injection and dedicated broker/container integration. `DeliveryProbe` is a test-only observer, not a replacement for the broker/DB source of truth, and does not guarantee exactly-once handling for other side effects.

**Why not use `Thread.sleep(1000)`?** Broker/consumer startup times in CI vary. Awaitility with an explicit timeout waits for the **business/observation condition**; if the consumer fails to process, the test FAILS meaningfully instead of relying on a lucky sleep.

### What to avoid in broker tests

- Do not assert "duplicate handled" merely because the DB has a marker after the first delivery.
- Do not share topics/groups/record keys across parallel suites without isolating brokers/contexts.
- Do not depend on test class order; isolate account/event IDs per test.
- Do not disable the listener and think you tested Kafka: direct tests and broker tests cover different scopes.
- Do not put `@Transactional` on the test client expecting it to roll back business writes committed by a Kafka listener thread.
- If a broker is cached across classes, align its lifecycle with the context rather than stopping the broker early while listeners remain active.

## 15. Expected results of the seven test methods

| Class | Test | Expected DB/exception outcome |
| --- | --- | --- |
| Direct | `sameEventTwiceChangesBalanceOnlyOnce` | 1000 + 250 = **1250**, 1 marker |
| Direct | `twoDifferentEventIdsAreTwoLegitimateCredits` | 1000 + 100 + 200 = **1300**, 2 markers |
| Direct | `sameEventIdWithChangedAmountIsAConflict` | Conflict exception, balance **1150** |
| Direct | `failedBusinessUpdateRollsBackMarkerSoRetryCanWork` | Attempt 1 marker 0; after creating account, balance **700**, 1 marker |
| Direct | `malformedJsonNeverChangesBusinessBalance` | Invalid JSON, balance remains **1000** |
| Direct | `nonPositiveDeltaIsRejectedBeforeMarker` | Invalid input, balance remains **1000**, 0 markers |
| Broker | `twoKafkaDeliveriesWithSameEventIdCreditOnlyOnce` | Observed APPLIED + DUPLICATE; balance **1250**, 1 marker |

These are **expectations derived from the code logic**, not recorded JUnit execution output. The code contains no `System.out.println`, and Kafka server/Gradle logs vary by environment.

To evaluate throughput or races for the same event across **two real consumer instances**, embedded Kafka + H2 is only a baseline. Add stress tests with real PostgreSQL/MySQL, at least two consumer workers, unique-key contention, rollbacks/timeouts, and proper isolation.

## 16. Testing concurrency: unique index is central, not `synchronized`

A broken way to fix "duplicate messages":

~~~java
// Unsafe across multiple pods or multiple JVMs:
synchronized void handle(CreditEvent e) {
    if (!seenInMemory.contains(e.eventId())) {
        applyBusinessEffect(e);
        seenInMemory.add(e.eventId());
    }
}
~~~

`synchronized` only locks one object inside a single JVM. With three Kubernetes pods, each pod has separate memory. On process restart, `seenInMemory` disappears. On cache eviction, old duplicates get processed again. Redis `SETNX` can assist coordination, yet must handle atomicity with DB effects and TTL; a lock/cache key alone does not replace a unique constraint and transaction.

**Concurrency matrix to test against a real DB:**

1. Two workers simultaneously INSERT the marker (same scoped event ID) and try to UPDATE the balance.
2. One transaction commits; the other gets a duplicate (or retries on lock/deadlock).
3. Balance increases only once.
4. Two distinct event IDs on the same account both apply fully (atomic SQL increment prevents lost updates).
5. One worker crashes mid-transaction: DB rolls back both marker and effect; the other worker or retry can succeed.
6. One worker commits and crashes before ack: replay is a no-op.

Use `CountDownLatch`/`CyclicBarrier` to force controlled interleavings when testing races instead of `Thread.sleep` "hoping" two threads collide. Add timeouts to prevent hangs. With PostgreSQL Testcontainers, verify real SQL states, unique violations, and lock waits; H2 does not represent all PostgreSQL behavior.

### Why use an atomic SQL UPDATE?

This code risks a lost update:

~~~java
long balance = jdbc.queryForObject(
        "SELECT balance_cents FROM credit_accounts WHERE account_id=?",
        Long.class, accountId
);
jdbc.update(
        "UPDATE credit_accounts SET balance_cents=? WHERE account_id=?",
        balance + amount, accountId
);
~~~

Two transactions both read balance 1000 and write 1100 and 1200 respectively: the final result can be **1200 instead of 1300**. The main example uses `SET balance_cents = balance_cents + ?`, letting the database handle atomic updates/locking. Idempotency keys and atomic increments solve **two different problems**: duplicate events and concurrent distinct events.

## 17. Never mark processed before business success

A dangerous bug:

~~~text
BEGIN TX #1
  INSERT credit_inbox(eventId)       -> COMMIT
BEGIN TX #2
  UPDATE business balance            -> FAIL / ROLLBACK

Kafka retries eventId:
  sees marker already exists -> skip
=> business effect is permanently lost.
~~~

This can happen if the marker service uses `@Transactional(propagation=REQUIRES_NEW)` while the business update participates in an outer transaction that rolls back. **Never use an independent transaction for the marker** when the marker means "the business effect committed".

The right pattern: marker and business update in the **same DB transaction**, as in `CreditProcessor.apply`. If an event modifies **multiple rows** in the same database, keep all of them inside one transaction. If an effect is an HTTP call outside the DB, a JDBC transaction cannot roll back the HTTP call: design dedicated API idempotency/outboxes/workflows.

## 18. Business side effects outside the database: email, payments, and publishing events

A unique inbox + DB transaction protects the example's balance update. It **does not by itself protect**:

- Sending emails/SMS/push notifications.
- Calling a payment provider, shipping API, or credit limit service.
- Publishing downstream Kafka/RabbitMQ events.
- Writing files/object storage or invalidating external caches.
- Calling another microservice that already committed its own transaction.

Three error-prone orderings:

| Ordering | Crash happens after which step? | Risk |
| --- | --- | --- |
| Call payment before DB commit | Payment succeeds, DB rolls back | Retry may charge again |
| DB commits marker before sending email | Process crashes after DB commit, before send | Event skipped on redelivery, **email lost** |
| Send email before committing marker | Email succeeds, DB rolls back | Redelivery may send email twice |

### Transactional outbox pattern

In the **same transaction as the business effect and inbox marker**, INSERT a row into an `outbox` table holding the event to send. A separate publisher/relay reads the outbox, publishes to the broker, and marks delivered/advances. An outbox guarantees **the event to send is recorded atomically with the DB commit**, not that the relay will never publish twice (e.g., sends and crashes before marking). **Downstream consumers must still be idempotent.**

~~~text
DB TX:
  INSERT inbox E
  UPDATE balance +250
  INSERT outbox O (CreditApplied)
  COMMIT

Relay:
  READ outbox O
  PUBLISH O
  MARK SENT (can crash in between)

Downstream:
  receives O one or more times
  uses idempotency key to apply effect only once
~~~

For payment providers with idempotency-key APIs, send a **stable key tied to the logical payment** and adhere to provider retention contracts. Never automatically use Kafka offsets or a fresh UUID per retry as a payment idempotency key, as duplicate charges can still occur.

### Transaction synchronization is not distributed ACID

`@TransactionalEventListener(AFTER_COMMIT)` delays callbacks until after the DB commits, avoiding publishing before commit. However, crashing **after DB commit and before the callback** can still lose the event; when durable messaging is required, an outbox is usually better. Kafka transactions do not automatically enclose external APIs or DB commits. 

## 19. Retries: transient errors differ from permanent errors

| Error category | Example | Reference policy |
| --- | --- | --- |
| Transient | DB connection timeout, brief broker/network blip, retryable deadlock | Bounded retries + backoff/jitter, keep same idempotency key |
| Temporary business dependency | Account not yet created because event arrived early | Bounded retries or pending queue, consider event ordering |
| Conflict/payload corruption | Same event ID with different account/amount | Do not retry infinitely; DLT/alert, investigate producer |
| Malformed JSON/schema | Unparseable event | DLT/parking lot and replay after fix |
| Permanent authorization | Event from unauthorized source | Reject/quarantine, security audit |
| Unbounded downstream throttling | HTTP 429 | Honor `Retry-After`, rate limits, timeouts, circuit breaker |

Spring Kafka offers `DefaultErrorHandler` for blocking retries/error handling and `@RetryableTopic` for non-blocking retries/topic chains. **Do not turn both on mechanically**; know the exact attempt count, backoff, DLT naming, acknowledgment/offset policy, and library behavior. Spring Kafka 3.3 docs state **non-blocking retries cannot be combined with Kafka container transactions**; do not copy a `@RetryableTopic` example and promise end-to-end container transactions without verifying. 

### What is a Dead Letter Topic?

A DLT stores messages that failed processing per policy so operators can investigate/replay. A DLT **does not** mean "business effect was applied". An event in the DLT may have already produced **partial** side effects if the code was non-atomic. When replaying from a DLT, **preserve the logical event ID**; changing the ID makes the system treat it as a brand-new event and repeat side effects.

### When to ack

- Ack/commit offset after the business transaction commits or a safe duplicate is confirmed.
- If the listener throws before completion, the error handler decides retry/DLT per config.
- Never swallow every exception and return success; the broker could skip an **unprocessed** event.
- If a listener returns async completion to the framework, understand exact ack timing and lifecycles.
- With manual acknowledgment, handle thread/ack modes per API; never call `acknowledge()` right after parsing JSON and run business effects later.

## 20. Same `eventId` with different payload: treat as an error

An existence-only "dedup" implementation:

~~~java
if (inboxExists(eventId)) {
    return; // too broad: swallows event ID collisions with different content
}
~~~

If a producer accidentally reuses an ID across two commands, or an event was altered during replay, a valid event gets silently dropped. The example stores `account_id` and `delta_cents` alongside the marker. On duplicate key:

- **Same ID + same business payload:** treat as redelivery of the logical event, return success/no-op.
- **Same ID + different business payload:** `Conflicting eventId` error; alert/DLT.
- **Different ID + same payload:** two independent events unless a separate business key requires processing only once.

Production should also store `tenantId`, `eventType`, `schemaVersion`, source, a canonical payload digest, or a normalized business fingerprint. Avoid comparing raw JSON byte-for-byte when field ordering, whitespace, or versions can change while business semantics stay identical.

### When event versions exist

If v1 and v2 events represent the same logical event, decide how to compare payloads: normalize to canonical business semantics before comparing, or store version and reject conflicts conditionally. Never mutate an old event by keeping the same ID while changing money/quantity semantics without an explicit migration contract.

## 21. How long must idempotency markers live?

A `processed_events`/`credit_inbox` table grows continuously. Deleting markers too soon to save storage can cause replayed old messages to apply business effects a second time.

Example:

~~~text
Day 1: event E applied, marker E stored in DB.
Day 8: cleanup deletes marker E per 7-day TTL.
Day 9: backfill/replay E from Kafka archive.
Result: E treated as new -> balance increases a 2nd time.
~~~

Deduplication TTL must at least span **the real replay/retry window required by the business contract**. For money, you may need very long marker retention or uniqueness tied to an immutable business ledger with matching retention, rather than a short TTL. If data retention laws require purging identifying data, design secure keys/canonical digests/ledgers and explicit replay policies.

You can partition the inbox table by time, archive periodically, or enforce business-level uniqueness constraints, ensuring cleanup never breaks idempotency within the guaranteed window.

**Idempotency is not "forever exactly-once"** if the system deletes event-recognition records after some cutoff.

## 22. Message ordering, partition keys, and out-of-order events

Deduplication only solves **the same event appearing multiple times**. It does not solve ordering between **two distinct events**:

~~~text
Event E1: order status = PAID, version=2
Event E2: order status = SHIPPED, version=3

Due to retry/DLT, consumer may see E2 before E1.
If status writes ignore version, replaying E1
could revert SHIPPED back to PAID.
~~~

In Kafka, the same key typically maps to the same partition, preserving **record order within one partition** for a normal consumer group. Yet multiple producer paths, retry topics, concurrent side effects, manual replays, and cross-topic deliveries can invert **business** order. For state machines, use **aggregate versions** / compare-and-set / optimistic locking:

~~~sql
UPDATE orders
SET status = ?, version = ?
WHERE order_id = ? AND version = ?;
~~~

This is **illustrative SQL** (not part of the credit example schema). If UPDATE affects 0 rows, classify duplicate/older event/out-of-order/missing gap. Never automatically treat every 0-row update as success; you may need to wait for an earlier version or trigger reconciliation.

### Kafka partition keys and idempotency

In the embedded Kafka test, both records are sent with the **same account key**. The test has a single partition, making the `APPLIED` then `DUPLICATE` sequence easy to observe. When scaling to multiple partitions and consumer instances, unique DB constraints remain essential; partition ordering alone does not protect against duplicate publishes on other topics or cross-resource side effects.

## 23. Consumer/group/tenant scope of inbox markers

The `PRIMARY KEY(consumer_name,event_id)` key lets projection `credit-balance-v1` deduplicate independently. If you add another projection such as fraud detection or email notifications, it needs to process the same event once for **its own projection**. Never share one "global processed" column across all consumers, which would cause the second consumer to skip the event.

In multi-tenant systems:

~~~text
tenant_id | consumer_name      | event_id
-------------------------------------------------
tenant-A  | credit-balance-v1  | E
tenant-B  | credit-balance-v1  | E
tenant-A  | audit-v1           | E
~~~

This is an **illustrative table**. Keys may include tenant ID, event type, and projection version depending on the scope where the producer guarantees ID uniqueness. Even if `eventId` is globally unique across the entire system, you still must distinguish consumers/projections. If a business effect must be unique by payment transaction ID, add a separate business unique constraint to block **two different event IDs** for the same payment.

**Never change key scoping after migration without handling history.** Rebuilding projection v2 may require replaying the same event IDs for a new read model, yet that must never re-charge a monetary transaction already recorded in ledger v1.

## 24. Testing failure injection and crash windows

A serious idempotence test suite needs more than calling `onMessage(E)` twice. Matrix:

| Failure point / scenario | What to verify |
| --- | --- |
| Before INSERT marker | No effect; retry safe |
| After INSERT marker yet **before UPDATE**, same DB transaction | Rolls back marker; retry still applies |
| After UPDATE yet **before COMMIT** | Rolls back both marker and effect |
| Right after DB COMMIT, before Kafka ack | Redelivery no-ops; no double credit |
| Two threads INSERT same event ID | Only one tx commits effect |
| Two distinct events on same account | No lost update; sum of both deltas |
| Business effect DB commits, outbound email unsent | Do not assume email was sent; needs outbox |
| Outbox publish succeeds, mark sent fails | Outbox replay may publish twice; downstream dedups |
| Same ID, changed account/amount | Conflict detected, not silently skipped |
| Poison JSON/schema v2 | DLT and alert per policy, no endless retry |
| Replay from DLT/backup | Preserves `eventId`, adequate marker retention |
| Multi-tenant same external event key | No cross-tenant skipping |
| Parallel test suites | Data/consumer groups/topics do not overwrite each other |

The direct test in section 13 proves marker rollback for a missing account. The embedded test in section 14 proves **two Kafka deliveries of the same logical event**. To prove the exact crash window, add fault-injection tests between DB commit and offset commit, such as killing/pausing the consumer/container and restarting with the same consumer group/offset in Testcontainers Kafka + PostgreSQL.

**Never assert after `Thread.sleep` as proof both messages were processed.** The broker test used `DeliveryProbe` to wait for both outcomes combined with DB assertions.

## 25. RabbitMQ: ack/nack also leads to duplicates

In Spring AMQP/RabbitMQ, a listener can finish processing yet lose its connection/channel before the broker receives ACK. The broker can requeue and redeliver the same logical message. `AcknowledgeMode.AUTO`/`MANUAL`, prefetch, retry interceptors, dead-letter exchanges, and requeue policies shape behavior; they **do not** replace business deduplication.

Illustrative skeleton:

~~~java
@RabbitListener(queues = "credit-events")
public void onRabbitMessage(String json) {
    creditKafkaListener.onMessage(json);
}
~~~

This is **only an adapter example**, not a runnable file in the main project: it needs `spring-rabbit`, imports, queue declarations, and retry/ack config. Calling `onMessage` directly here reuses the demo logic, whereas production should extract a core business handler out of transport adapters so Kafka and Rabbit do not call each other directly.

The same inbox design works for Rabbit, SQS, Pulsar, or webhook retries as long as they provide a **stable logical idempotency key**. If a broker-generated delivery ID changes on retry, never substitute it for a business `eventId` without understanding the contract.

## 26. Observability and alerting for deduplication/side effects

Never log only "message received" and call it success. Meaningful metrics:

- `messaging.delivery.attempts`: how many times the consumer received records.
- `messaging.business.applied`: how many logical events committed business effects.
- `messaging.duplicate.skipped`: how many deliveries no-oped due to valid markers.
- `messaging.conflict.detected`: same key with different payload; investigate producer.
- `messaging.processing.failed`: failures not yet safely resolved.
- `messaging.dlt.count`: events routed to DLT per policy.
- `messaging.lag`, `processing.latency`, `db.lock.wait`, `outbox.pending`: system health.

Metric definitions must clarify whether they **count deliveries or logical events**. One event received three times might yield 3 attempts, 1 applied, and 2 skipped. Never count 3 applied just because the listener was invoked 3 times.

Logs should include `eventId`, `consumerName`, tenant, correlation ID, and account reference per security policy, while excluding sensitive payment tokens/PII. For end-to-end tracing, propagate trace context, yet **trace IDs must never default to idempotency keys**.

### Alerts that avoid false positives

Rising duplicate counts can be normal during bursts/rebalances, whereas rising conflicts are abnormal. Alert on duplicate ratio, lag, and processing latency; check whether a valid replay/campaign is underway or an incident occurred. For DLTs, maintain a triage/replay playbook that preserves logical event IDs.

## 27. Common mistakes and how to fix them

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Balance doubles on Kafka redelivery | No marker/business key stored | Unique inbox + atomic tx |
| Two workers both see "not processed" | Check-then-act race | Unique constraint; INSERT marker first |
| Subsequent SQL fails after duplicate key exception | Caught unique violation **inside** PostgreSQL tx | Catch outside transactional proxy |
| Marker exists yet business update failed | Marker and effect in different txs / `REQUIRES_NEW` marker | Same DB transaction |
| Same event ID with different payload skipped | Checked marker existence only | Store/compare canonical business payload |
| Two legitimate transactions merged | Key = account+amount with no separate event ID | Stable unique ID per logical action |
| Retry charges external API again | Failed to pass stable provider idempotency key | Provider key + workflow/outbox |
| Kafka EOS yet DB still duplicates | EOS covers only Kafka transactions/offsets in scope | DB inbox/business idempotency |
| Direct test PASSES, broker path FAILS | Wrong listener/group/serializer/topic config | `@EmbeddedKafka`/real broker test |
| Test sees balance 1250 before 2nd duplicate arrives | Asserted DB before 2nd delivery completed | Await both deliveries/outcomes |
| DLT replay credits money again | Marker purged too early or event ID changed | Retention/replay contract |
| Lost Rabbit ack causes requeue | At-least-once delivery | Idempotent consumer |
| Concurrent distinct event IDs lose updates | Unlocked read-modify-write | Atomic SQL UPDATE/optimistic locking |
| `@Transactional` test misses persisted effects | Test tx rolled back/read wrong thread | Explicit commit and out-of-tx query |
| Error handler retries malformed JSON infinitely | Permanent errors not classified | DLT/parking lot + alert |
| `@RetryableTopic` + Kafka container tx misbehaves | Features do not combine per docs | Redesign retry/tx |
| DB marker deduplicates yet email sends twice | Email outside DB tx | Outbox + downstream/provider dedup |
| Two distinct projections skip each other | Global event marker | Scope by consumer/tenant/version |
| CI flakes from shared topics/groups | Tests share brokers/offsets/state | Isolate topics/groups/fixture namespaces |

## 28. Pre-finalization checklist for Messaging tests

- [ ] Defined a stable logical event ID preserved across producer retries, redeliveries, and DLT replays?
- [ ] Distinguished same event ID from two distinct events sharing identical payload fields?
- [ ] Unique constraint enforced **in the database**, not only in Java/cache?
- [ ] Marker INSERT and business update execute in the **same DB transaction**?
- [ ] Duplicate-key errors handled **after** rollback of the failed transaction?
- [ ] Same ID + changed payload flagged as a conflict?
- [ ] Business failures roll back the marker so replays can succeed later?
- [ ] Never ack/commit offsets ahead of the DB commit?
- [ ] Never swallow unexpected exceptions and report delivery success?
- [ ] Tested the same event twice verifying balance changes only once?
- [ ] Tested two different IDs on the same account applying twice?
- [ ] Tested transaction rollback when account/business mutation fails?
- [ ] Tested malformed/poison events against retry/DLT policies?
- [ ] Included real/embedded broker tests beyond direct method tests?
- [ ] Async test awaits **both deliveries**, not only the first effect?
- [ ] Plan for testing concurrent unique inserts on production-like DBs?
- [ ] Side effects outside the DB (email/payment/Kafka publish) covered by idempotency/outbox strategies?
- [ ] Deduplication retention at least as long as the replay window requiring protection?
- [ ] Idempotency key scoped properly to tenant/consumer/aggregate?
- [ ] Out-of-order events protected with version/sequence guards?
- [ ] Retry/backoff/DLT distinguishes transient vs. permanent errors?
- [ ] Kafka producer idempotence/EOS not mistaken for database-level exactly-once?
- [ ] Test fixtures clean up without touching shared production resources?
- [ ] No brittle assertions tied to CI offsets/timing?
- [ ] Logs and metrics measure APPLIED/DUPLICATE/CONFLICT with clear semantics?

## 29. Running the test suite and reading results

With JDK 17+, Gradle Wrapper, and dependencies ready:

~~~bash
./gradlew test --tests "com.example.credit.CreditListenerDatabaseTest"
./gradlew test --tests "com.example.credit.CreditEmbeddedKafkaTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.credit.CreditListenerDatabaseTest"
.\gradlew.bat test --tests "com.example.credit.CreditEmbeddedKafkaTest"
~~~

There are **7 JUnit cases** across the two classes. `CreditListenerDatabaseTest` runs against H2 with Kafka listeners disabled from auto-starting; `CreditEmbeddedKafkaTest` starts an embedded broker (test scope), emits two duplicate messages, and waits for `APPLIED` and `DUPLICATE`.

**There is no fixed stdout from the sample code**, because it never calls `System.out.println`. Gradle/Kafka startup logs and test durations vary by environment. The results in the section 15 table are **analytical expectations from source code**, not execution logs captured during authoring. The code has not been compiled/run with JUnit in this environment, so execute it locally after copying all files and setting up the Gradle Wrapper.

The demo only protects **a single money addition inside an H2 transaction**. Before production, add real-DB transaction isolation, account limits, overflow guards, currency validation, event signatures, multi-tenant keys, outboxes, and provider-side idempotency for external effects.

**Conclusion:** Brokers can redeliver messages; sound consumers treat duplicates as expected. Use a **stable event ID**, **unique inbox marker + business mutation in the same transaction**, distinguish valid duplicates from payload conflicts, and **ack after success or safe no-op**. Tests must verify **business effects**, not just method call counts. For emails, payments, or downstream messages, a DB transaction alone is not enough: extend guarantees with outboxes/idempotency keys and test crash windows.

### Official Documentation

- [Apache Kafka — Delivery semantics and exactly-once limits](https://kafka.apache.org/design/)
- [Spring Kafka — Transactions, DB synchronization, and commit limits](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Testing Applications and @EmbeddedKafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka 3.3 — Non-Blocking Retries / @RetryableTopic and DLT](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic.html)
- [Spring Boot 3.5 — Kafka messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/kafka.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework 6.2 — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Boot 3.5.16 — JDK and Gradle requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)