# Testing Duplicates and Idempotency in Spring Kafka

## 1. Goal of the reliability test

In a system using **Spring Kafka**, the same business event can be received by a consumer **multiple times**. The cause is not necessarily a Kafka bug: producer retries, consumer retries, rebalances, process crashes, or dead-letter topic replays can all cause a business effect to be attempted again.

For example, a consumer handling a **CreditEvent** to add funds to an account:

~~~text
Event: eventId=credit-20261115-001
Account: ACC-001
Amount: +125.00

Kafka delivery 1  -> Consumer -> balance +125.00
Kafka delivery 2  -> Consumer -> balance +125.00  (WRONG if added again)
~~~

Without deduplication, after two deliveries the balance increases by **250.00** instead of **125.00**.

**Idempotency** means executing the same operation with the same identity produces **the same business outcome as executing it once**. In this lesson, what must be proven is not that Kafka delivers only one record, but that:

> Even if the same event is delivered to the consumer multiple times, the balance-credit effect is applied only once within the intended business scope.

This practice aims to:

- Understand how **duplicate delivery** differs from a **duplicate business event**.
- Design a **stable eventId**, deduplication table, and database transaction.
- Write tests proving receiving the same event multiple times produces the side effect only once.
- Test failures between database commit and Kafka offset commit, retries, and restarts.
- Test race conditions when two consumers/workers process duplicates concurrently.
- Test DLT replays, payload conflicts, mid-transaction failures, and messages with distinct eventIds.
- Use **PostgreSQL Testcontainers**, **Embedded Kafka**, or Kafka Testcontainers for reliable tests.
- Avoid assertions prone to false positives in asynchronous tests.

Examples target **Java 17, Spring Boot 3.x, Spring Kafka 3.x, Spring JDBC, and PostgreSQL**. The code can be structured into a real application; test sections explicitly state schema, fixture, and configuration prerequisites.

## 2. Why can a Kafka consumer see duplicates?

Each Kafka record has its own **topic, partition, and offset**. When a consumer in a consumer group finishes processing, it must commit the corresponding offset so Kafka tracks group progress. **Database writes** and **consumer offset commits** are typically two independent operations.

~~~text
Topic credit-events / partition 0 / offset 115
              |
              v
        Kafka consumer
              |
              v
      Write to database
              |
              v
      Commit Kafka offset
~~~

Suppose:

1. Consumer receives record at offset 115.
2. Consumer updates the balance and the database transaction commits.
3. JVM crashes **before** committing the Kafka offset.
4. After restart, the consumer group re-reads offset 115.
5. Consumer attempts to apply the same business operation again.

Kafka performed redelivery as designed to avoid losing processing; without application-level idempotency, the balance increases twice.

Other scenarios:

| Duplicate source | What happens? | Same Kafka offset? |
| --- | --- | --- |
| Crash after DB commit, before offset commit | Consumer re-reads old record | Usually same offset |
| Consumer retry via error handler/seek | Record is reprocessed | May be same offset |
| Consumer rebalance before offset commit | Another member receives uncheckpointed record | May be same offset |
| Producer or upstream resends business event | Two records carry the same eventId | Usually different offsets |
| DLT replay/re-drive | Event is republished from dead-letter topic | New topic/offset |
| Client resends event-creation request | Multiple business messages share operation ID | May have different topic/partition/offset |
| Operator resets offsets to backfill | Consumer re-reads history | Same old topic/partition/offset |

Thus **topic + partition + offset** is not always an adequate business deduplication key. Two Kafka records at different offsets can still represent **the same transaction**.

### At-least-once vs. exactly-once

In a typical workflow, Kafka consumers are designed around **at-least-once**: records may be reprocessed if offset progress has not been confirmed.

Kafka producers offer an **idempotent producer** feature that prevents certain duplicates from producer retries into the Kafka log within Kafka's supported bounds. Kafka transactions/exactly-once semantics also support Kafka-to-Kafka pipelines when properly configured.

However, **do not assume Kafka transactions guarantee exactly-once for side effects in PostgreSQL, HTTP APIs, or emails**. When the database and Kafka do not share a single atomic transaction, a failure window remains where a record can be redelivered after the side effect already committed.

The effective guarantee in this lesson is **at-least-once delivery + idempotent business processing**, not a promise that every record is ever seen once by the consumer.

## 3. Identifying the right identity to detect duplicates

Illustrative event:

~~~java
import java.math.BigDecimal;

public record CreditEvent(
        String eventId,
        String accountId,
        BigDecimal amount) {
}
~~~

JSON example:

~~~json
{
  "eventId": "credit-20261115-001",
  "accountId": "ACC-001",
  "amount": 125.00
}
~~~

**eventId** must be a stable identifier for **one business credit operation**. When a producer retries or republishes the same event, it must preserve the **original eventId** rather than generating a new UUID on each send.

Values that should not be used as the default deduplication key:

| Value | Problem |
| --- | --- |
| Kafka offset | Republished duplicates get a new offset |
| Kafka partition | Many distinct events share a partition |
| Consumer instance ID | Changes on rebalance/restart |
| Consumer receive timestamp | Each redelivery has a different timestamp |
| UUID generated inside consumer | Each delivery gets a new UUID, breaking dedup |
| Payload hash alone | Two legitimate transactions can have identical payloads |
| accountId alone | One account legitimately receives many credits |

**eventId** works when the domain guarantees one eventId represents strictly one operation. If upstream can emit two eventIds for the same transfer request, use a more stable **operationId/paymentId** from the business source, or combine with a unique constraint on a domain table.

In multi-tenant systems, scope may be **tenantId + operationId** rather than a global eventId. Uniqueness rules must be defined by the domain.

### Duplicate with same ID but different payload

Suppose we receive:

~~~text
Event A: eventId=credit-001, accountId=ACC-001, amount=125.00
Event B: eventId=credit-001, accountId=ACC-001, amount=999.00
~~~

Never silently ignore B as a valid duplicate. This may be an **identity contract violation**, an upstream bug, or an incident needing investigation. A sound design retains enough information to detect **same eventId with differing business payload**.

## 4. Conditions to verify in tests

For a valid event **E**:

**Basic idempotency**

~~~text
apply(E)
apply(E)

Final balance = Initial balance + E.amount
processed event count for E = 1
~~~

**Two distinct valid events**

~~~text
apply(E1)
apply(E2)   // E1.eventId != E2.eventId

Final balance = Initial + E1.amount + E2.amount
~~~

**Failure before database commit**

~~~text
apply(E) -> database error -> rollback
retry apply(E) -> success

Final balance = Initial + E.amount
processed event count for E = 1
~~~

**Failure after database commit but before offset commit**

~~~text
DB commit for E succeeds
Consumer crashes before Kafka offset commit
Kafka redelivers E
apply(E) detects existing marker and does not reapply

Final balance = Initial + E.amount
~~~

**Payload conflict**

~~~text
apply(E1: eventId=X, amount=125)
apply(E2: eventId=X, amount=999)

Second operation must not silently change balance.
Conflict must be surfaced and investigated.
~~~

**Concurrent duplicates**

~~~text
Worker A -> apply(E)
Worker B -> apply(E) at nearly the same time

Exactly one committed application to balance.
~~~

These scenarios should form a dedicated test suite, not just one test sending two messages and waiting a few seconds.

## 5. Why in-memory deduplication is insufficient

An error-prone approach:

~~~java
private final Set<String> seenEventIds =
        ConcurrentHashMap.newKeySet();

public void handle(CreditEvent event) {
    if (!seenEventIds.add(event.eventId())) {
        return;
    }

    updateBalance(event);
}
~~~

This has three fundamental flaws:

1. **Process restarts wipe the Set**, so post-crash redeliveries can credit the account again.
2. **Two consumer instances** do not share the same Set, so each instance can apply the same event.
3. If **seenEventIds.add** succeeds while **updateBalance** fails, the event is marked processed in RAM even though the business operation failed.

Even when storing dedup keys in Redis, if the marker write and database write live in two systems without a shared transaction, a failure window remains. Redis/caches can help as a load-shedding layer, yet for financial impacts the source of truth generally requires a **durable unique constraint** inside the same transaction as the business update.

## 6. Designing the deduplication table in PostgreSQL

We use two tables:

~~~sql
CREATE TABLE account_balance (
    account_id VARCHAR(80) PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL
);

CREATE TABLE processed_event (
    consumer_scope VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    account_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_scope, event_id)
);
~~~

Meaning:

- **account_balance** holds the committed business effect.
- **processed_event** holds a marker for an applied event.
- **PRIMARY KEY (consumer_scope, event_id)** guarantees only one transaction can insert a marker for the chosen identity.
- **account_id** and **amount** preserve a trace to catch cases where an eventId is reused for a different payload.
- **consumer_scope** is the **stable logical identity** of the processing type, not a pod ID. If multiple distinct business consumers need to process the same event, they can use separate scopes.

For example, scope **credit-ledger-v1** identifies a credit operation by the ledger service. Do not change scopes casually on every deploy, as changing scope prevents older messages from being recognized as duplicates.

### Dedup marker and business effect must share a transaction

Both operations must execute in the same database transaction:

~~~text
BEGIN TRANSACTION
    INSERT processed_event marker
    UPDATE account_balance
COMMIT TRANSACTION
~~~

If updating the balance fails, the transaction must **roll back the marker as well**. Otherwise, a retry sees the marker and skips an operation that never succeeded.

An anti-pattern:

~~~text
1. INSERT marker -> COMMIT
2. UPDATE balance -> ERROR

Retry sees marker, skips.
Balance never updated.                   (LOST PROCESSING)
~~~

Conversely, committing the balance update before persisting the marker is also risky: crashing between the two transactions causes retries to credit again.

## 7. Implementing idempotent CreditService with Spring JDBC

Example using **JdbcTemplate** and **@Transactional** with a real transaction manager governing both PostgreSQL tables.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreditService {

    private static final String SCOPE = "credit-ledger-v1";

    private final JdbcTemplate jdbc;

    public CreditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(CreditEvent event) {
        validate(event);

        int inserted = jdbc.update("""
            INSERT INTO processed_event (
                consumer_scope, event_id, account_id, amount
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT (consumer_scope, event_id) DO NOTHING
            """,
            SCOPE,
            event.eventId(),
            event.accountId(),
            event.amount());

        if (inserted == 0) {
            // Marker already exists. Verify business payload is unchanged.
            EventFingerprint original = jdbc.queryForObject("""
                SELECT account_id, amount
                FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                (rs, rowNum) -> new EventFingerprint(
                        rs.getString("account_id"),
                        rs.getBigDecimal("amount")),
                SCOPE,
                event.eventId());

            if (original == null
                    || !original.accountId().equals(event.accountId())
                    || original.amount().compareTo(event.amount()) != 0) {

                throw new IllegalStateException(
                        "Conflicting payload for eventId="
                        + event.eventId());
            }

            // Valid duplicate: do not update balance again.
            return;
        }

        int updated = jdbc.update("""
            UPDATE account_balance
            SET balance = balance + ?
            WHERE account_id = ?
            """,
            event.amount(),
            event.accountId());

        if (updated != 1) {
            // RuntimeException rolls back the marker too.
            throw new IllegalStateException(
                    "Account not found for eventId="
                    + event.eventId());
        }
    }

    private static void validate(CreditEvent event) {
        Objects.requireNonNull(event, "event");

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.accountId() == null
                || event.accountId().isBlank()
                || event.amount() == null
                || event.amount().signum() <= 0) {

            throw new IllegalArgumentException(
                    "Invalid CreditEvent");
        }
    }

    private record EventFingerprint(
            String accountId,
            BigDecimal amount) {
    }
}
~~~

In production, add length limits, tenant authorization/scoping, overflow or decimal-precision checks, currency-specific amount validation, and rate limiting. This example focuses purely on idempotency.

### Why INSERT first and then UPDATE?

PostgreSQL's **PRIMARY KEY** combined with **ON CONFLICT DO NOTHING** decides which transaction is allowed to apply the effect for a given eventId. Two concurrent requests inserting the same key are coordinated by the database on the unique constraint. If the first transaction rolls back, the other proceeds to insert; if the first commits, the other observes conflict.

When **inserted = 1**, the current transaction owns performing the update. When **inserted = 0**, a marker already exists and the payload must be checked before skipping.

Under PostgreSQL's default **READ COMMITTED**, this pattern behaves cleanly for concurrent duplicates. If a project changes isolation levels, uses R2DBC/Reactive, or separates marker and balance into different databases, re-evaluate atomicity and race cases.

### Why not rely solely on synchronized?

**synchronized** only protects threads within the same JVM on the same object. Kafka consumers can run across multiple pods or processes; a durable database lock/constraint is visible to all instances.

### Why use BigDecimal?

Money should never be added using float/double. **NUMERIC** in PostgreSQL and **BigDecimal** in Java handle decimal arithmetic accurately within type limits and business rules.

## 8. Kafka listener: commit database before completing record handling

The listener parses JSON into CreditEvent and calls the service:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class CreditListener {

    private final ObjectMapper mapper;
    private final CreditService creditService;

    public CreditListener(
            ObjectMapper mapper,
            CreditService creditService) {

        this.mapper = mapper;
        this.creditService = creditService;
    }

    @KafkaListener(
            topics = "credit-events",
            groupId = "credit-ledger-v1")
    public void onMessage(ConsumerRecord<String, String> record)
            throws JsonProcessingException {

        CreditEvent event =
                mapper.readValue(record.value(), CreditEvent.class);

        // Call through Spring-managed service bean so @Transactional
        // applies. When this method returns normally, the service's
        // database transaction has already committed.
        creditService.apply(event);
    }
}
~~~

Illustrative configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true
    listener:
      ack-mode: record
~~~

With **AckMode.RECORD** and **enable-auto-commit=false**, the listener container manages committing the offset after the record finishes processing per configuration. When **service.apply** returns normally, the database transaction is already committed before the listener returns.

However, **database commit and Kafka offset commit are not one atomic transaction**. If the JVM crashes after the database commits and before the offset commits, the record can be redelivered. The **processed_event** table prevents replays from crediting twice.

**Never commit/ack an offset before business effects are confirmed.** If you ack early and the database update later fails, Kafka may consider the record processed and skip retries, losing the operation.

### Distinguish data errors from transient errors

- **Database timeout/deadlock:** typically requires retries with appropriate backoff.
- **Missing account:** requires a domain policy; never treat as a duplicate.
- **Unparseable JSON:** never reaches the service; requires recoverer/DLT or appropriate error workflow.
- **Same eventId with different amount:** this is a **payload conflict**, requiring alerts or quarantine; never add again and never treat as valid success.
- **Duplicate with same eventId and payload:** service returns normally, letting the container commit progress.

## 9. Failure boundaries and expected behavior

Build a failure-window table before writing tests:

| When failure occurs | DB state | Offset state | On replay |
| --- | --- | --- | --- |
| Before marker INSERT | Unchanged | Uncommitted | Processed as first time |
| After INSERT, before UPDATE, tx rolls back | Both marker and balance roll back | Uncommitted | Processed as first time |
| After UPDATE, before DB commit, tx rolls back | Both marker and balance roll back | Uncommitted | Processed as first time |
| After DB commit, before offset commit | Marker and balance committed | Uncommitted | Sees duplicate, does not add again |
| After offset commit | Marker and balance committed | Committed | Normally no automatic replay |
| Offset commit before DB commit | Side effect may be missing | Committed | Risks lost processing; avoid this design |

**At-least-once + idempotency** mainly protects the **DB committed, offset uncommitted** window. It does not replace testing that the DB transaction actually rolls back when a business operation fails.

Especially for events with effects outside the database (emails, HTTP, transfers to external systems), a JDBC transaction does not roll back those effects. Use idempotency keys at the receiving system, an outbox, or an appropriate state machine.

## 10. Building a test pyramid: what to test at each layer?

A reliable suite has more than one test type:

| Tier | Real components | What it verifies |
| --- | --- | --- |
| **Unit test** | Pure logic, fake repositories where fitting | Duplicate/conflict handling decisions |
| **Database integration test** | Real PostgreSQL or Testcontainers | Unique constraints, transaction rollbacks, concurrent inserts |
| **Kafka integration test** | Test broker + database | Two Kafka records with same eventId, offsets, and listener |
| **Failure/recovery test** | Kafka, database, process restarts | Replay after crash, rebalances, uncommitted offsets |
| **DLT/re-drive test** | Error handler, DLT, replay workflow | Reprocessing records already applied or quarantined |
| **Load/soak test** | Production-like environment | Races, lag, marker storage cost, and retention |

**Mocking KafkaTemplate does not prove the broker stored two records.** **Mocking the repository does not prove PostgreSQL's unique constraint holds under concurrent transactions.** For idempotency, the two most critical layers are **database integration** and **Kafka integration**.

## 11. Service integration testing with PostgreSQL Testcontainers

Testing CreditService directly separates idempotency logic bugs from Kafka listener, offset, or serializer issues.

Spring Boot Test skeleton:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class CreditServiceIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    CreditService creditService;

    @Test
    void applyingSameEventTwiceChangesBalanceOnce() {
        String accountId = "acc-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
                accountId,
                new BigDecimal("100.00"));

        CreditEvent event = new CreditEvent(
                eventId,
                accountId,
                new BigDecimal("25.00"));

        creditService.apply(event);
        creditService.apply(event);

        BigDecimal balance = jdbc.queryForObject(
                "SELECT balance FROM account_balance WHERE account_id = ?",
                BigDecimal.class,
                accountId);

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                Integer.class,
                "credit-ledger-v1",
                eventId);

        assertThat(balance)
                .isEqualByComparingTo("125.00");
        assertThat(markers).isEqualTo(1);
    }
}
~~~

**Prerequisites to run:** the test database must have both tables created per the schema in section 6, e.g., via Flyway, Liquibase, or a migration fixture. Spring Boot Test, Testcontainers PostgreSQL/JUnit Jupiter, and the PostgreSQL JDBC driver must be in the project dependencies.

Use **random eventId/accountId values per test** to avoid fixture collisions. Do not wipe entire shared tables while tests run in parallel; truncating tables affects concurrent tests.

### Why not put @Transactional on the test itself and trust the result?

If a test method has `@Transactional` that rolls back by default at exit, it can mask the service's actual commit behavior or create a different transaction boundary than production consumers. Design tests to read **committed** state, and when testing multiple transactions or concurrent requests, avoid a test-wide transaction warping boundaries.

## 12. Testing that two distinct eventIds apply twice

Idempotency must never mistake **two legitimate events with the same amount/account** for a duplicate.

~~~java
@Test
void differentEventIdsApplyIndependently() {
    String accountId = "acc-" + UUID.randomUUID();

    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            accountId,
            new BigDecimal("100.00"));

    CreditEvent first = new CreditEvent(
            "evt-" + UUID.randomUUID(),
            accountId,
            new BigDecimal("25.00"));

    CreditEvent second = new CreditEvent(
            "evt-" + UUID.randomUUID(),
            accountId,
            new BigDecimal("25.00"));

    creditService.apply(first);
    creditService.apply(second);

    BigDecimal balance = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE account_id = ?",
            BigDecimal.class,
            accountId);

    assertThat(balance).isEqualByComparingTo("150.00");
}
~~~

If a system uses only **accountId + amount** or a payload hash as its dedup key, this test will fail because two real transactions are merged into one. Tests must confirm **legitimate events are not mistakenly dropped**.

In payment domains, also clarify whether two different eventIds carrying the same paymentId are two valid events or an upstream duplicate. If they are simply two emissions of the same payment, dedup must rely on **paymentId/operationId**, not merely technical eventId.

## 13. Testing rollback: marker must not survive when business update fails

A dangerous bug occurs when inserting the marker before updating the balance, and the target account does not exist.

~~~java
@Test
void rollsBackMarkerWhenBalanceUpdateFails() {
    String eventId = "evt-" + UUID.randomUUID();
    String missingAccount = "missing-" + UUID.randomUUID();

    CreditEvent event = new CreditEvent(
            eventId,
            missingAccount,
            new BigDecimal("25.00"));

    assertThatThrownBy(() -> creditService.apply(event))
            .isInstanceOf(IllegalStateException.class);

    Integer markerCount = jdbc.queryForObject("""
            SELECT COUNT(*)
            FROM processed_event
            WHERE consumer_scope = ? AND event_id = ?
            """,
            Integer.class,
            "credit-ledger-v1",
            eventId);

    assertThat(markerCount).isZero();

    // Fix the infrastructure/business precondition then retry.
    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            missingAccount,
            new BigDecimal("100.00"));

    creditService.apply(event);

    BigDecimal balance = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE account_id = ?",
            BigDecimal.class,
            missingAccount);

    assertThat(balance).isEqualByComparingTo("125.00");
}
~~~

This test proves **the marker and business update share a transaction** in the test setup. If the marker persisted in a separate transaction, `markerCount` would be 1 after failure and the retry would skip, losing the operation.

In Spring, `@Transactional` takes effect when calls go through a **Spring proxy** and the right transaction manager. In the example, CreditListener calls a separate service bean, avoiding self-invocation. Never assume a `@Transactional` method called internally on the same object is intercepted by a proxy.

## 14. Testing same eventId with different data

A good idempotent consumer catches **ID collisions with mismatched payloads**:

~~~java
@Test
void rejectsChangedPayloadWithSameEventId() {
    String accountId = "acc-" + UUID.randomUUID();
    String eventId = "evt-" + UUID.randomUUID();

    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            accountId,
            new BigDecimal("100.00"));

    creditService.apply(new CreditEvent(
            eventId, accountId, new BigDecimal("25.00")));

    assertThatThrownBy(() -> creditService.apply(
            new CreditEvent(
                    eventId,
                    accountId,
                    new BigDecimal("999.00"))))
            .isInstanceOf(IllegalStateException.class);

    BigDecimal balance = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE account_id = ?",
            BigDecimal.class,
            accountId);

    assertThat(balance).isEqualByComparingTo("125.00");
}
~~~

When the consumer encounters a conflict on Kafka, apply an appropriate policy: route to DLT/quarantine, alert on data inconsistency, and do not endlessly auto-retry unrecoverable errors. **Never swallow the exception and merely log "duplicate ignored"**, because that hides events sharing an ID with different data.

If payloads have many business fields, you can store a **payload fingerprint/canonical hash** alongside the marker, provided formatting/fields are canonicalized and collision limits understood. At minimum, compare the fields that determine side effects.

## 15. Testing concurrent duplicates with two threads

A classic bug of non-transactional deduplication is check-then-act:

~~~text
Thread A: SELECT marker -> none
Thread B: SELECT marker -> none
Thread A: UPDATE balance
Thread B: UPDATE balance
Thread A: INSERT marker
Thread B: INSERT marker (unique error)
~~~

Even though B fails on the unique constraint at the end, the balance may already have been credited twice if the update ran in a separate transaction. Therefore, use **atomic marker claim + business update in the same transaction**.

Tests can use CountDownLatch so two threads invoke the service simultaneously:

~~~java
@Test
void concurrentDuplicatesApplyOnlyOnce() throws Exception {
    String accountId = "acc-" + UUID.randomUUID();
    String eventId = "evt-" + UUID.randomUUID();

    jdbc.update(
            "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
            accountId,
            new BigDecimal("100.00"));

    CreditEvent event = new CreditEvent(
            eventId, accountId, new BigDecimal("25.00"));

    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch go = new CountDownLatch(1);

    try {
        Callable<Void> call = () -> {
            go.await();
            creditService.apply(event);
            return null;
        };

        Future<Void> first = pool.submit(call);
        Future<Void> second = pool.submit(call);

        go.countDown();

        first.get(15, TimeUnit.SECONDS);
        second.get(15, TimeUnit.SECONDS);

        BigDecimal balance = jdbc.queryForObject(
                "SELECT balance FROM account_balance WHERE account_id = ?",
                BigDecimal.class,
                accountId);

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                Integer.class,
                "credit-ledger-v1",
                eventId);

        assertThat(balance).isEqualByComparingTo("125.00");
        assertThat(markers).isEqualTo(1);
    } finally {
        pool.shutdownNow();
    }
}
~~~

The test file must import **java.util.concurrent** classes and **UUID**. This is an integration test against real PostgreSQL so unique constraints and competing transactions are verified.

**Do not place `@Transactional` on the entire test** in a way that leaves fixtures uncommitted while two workers run in separate transactions, because workers will not see the newly inserted account. Commit fixtures before starting the two threads.

For multi-JVM/pod systems, add production-like tests with two consumer processes or multiple listener instances. Thread-level tests do not verify full rebalance and consumer group behavior, though they test the core database concurrency point.

## 16. Embedded Kafka + PostgreSQL: testing two Kafka records with the same eventId

Service tests in prior sections prove database logic. To verify **the listener actually receives duplicates from Kafka**, use **@EmbeddedKafka** for the broker and PostgreSQL Testcontainers for the DB.

Illustrative integration configuration:

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@EmbeddedKafka(
        partitions = 1,
        topics = "credit-events",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@SpringBootTest(properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.ack-mode=record"
})
class CreditListenerKafkaIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void duplicateKafkaRecordsApplyCreditOnce() throws Exception {
        String accountId = "acc-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO account_balance(account_id, balance) VALUES (?, ?)",
                accountId,
                new BigDecimal("100.00"));

        CreditEvent event = new CreditEvent(
                eventId, accountId, new BigDecimal("25.00"));

        String json = mapper.writeValueAsString(event);

        kafkaTemplate.send(
                "credit-events", accountId, json)
                .get(10, TimeUnit.SECONDS);

        long secondOffset = kafkaTemplate.send(
                "credit-events", accountId, json)
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata()
                .offset();

        // Do not just wait for balance = 125: that can already hold
        // right after record 1, before record 2 is processed.
        // Wait for the consumer group to commit past record 2's offset.
        TopicPartition partition =
                new TopicPartition("credit-events", 0);

        await().atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    try (AdminClient admin = AdminClient.create(
                            Map.of(
                                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                                embeddedKafka.getBrokersAsString()))) {

                        var offsets = admin.listConsumerGroupOffsets(
                                "credit-ledger-v1")
                                .partitionsToOffsetAndMetadata()
                                .get(5, TimeUnit.SECONDS);

                        var committed = offsets.get(partition);
                        assertThat(committed).isNotNull();
                        assertThat(committed.offset())
                                .isGreaterThan(secondOffset);
                    }
                });

        BigDecimal balance = jdbc.queryForObject(
                "SELECT balance FROM account_balance WHERE account_id = ?",
                BigDecimal.class,
                accountId);

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_event
                WHERE consumer_scope = ? AND event_id = ?
                """,
                Integer.class,
                "credit-ledger-v1",
                eventId);

        assertThat(balance).isEqualByComparingTo("125.00");
        assertThat(markers).isEqualTo(1);
    }
}
~~~

This illustrative test has the following deployment prerequisites:

1. Dependencies include **spring-kafka-test**, **Testcontainers PostgreSQL/JUnit**, **Awaitility**, Jackson, PostgreSQL driver, and Spring Boot Test.
2. Both tables must exist via migrations/fixtures on the test database.
3. The test topic has **one partition** to simplify observing partition 0; with multiple partitions, use the exact partition returned by the second record's **RecordMetadata**.
4. The listener must use **groupId=credit-ledger-v1**, the same topic, and String value deserializer.
5. Avoid reusing consumer groups/topics from other suites, since committed offsets may belong to prior records. Isolate contexts/brokers/topics per suite.
6. If the project configures a custom KafkaListenerContainerFactory with a different ack mode/error handler, the test must use the configuration matching the production execution path.

### Why wait for committed offset instead of only waiting for balance?

An assertion like:

~~~java
await().untilAsserted(() ->
        assertThat(readBalance(accountId))
                .isEqualByComparingTo("125.00"));
~~~

can pass after the first record. The second record may **not have been processed by the consumer yet**; the test exits early and fails to prove idempotency.

Once we observe the group's committed offset **advance past the second record's offset** when both records share a partition, we know the consumer group processed through both messages per configuration. Only then should we read the final database state. With error handlers that can recover/skip records, also verify processing signals and recovery policies so a test never passes simply because a record was skipped without running the logic.

Another option is placing a **test probe** where the listener finishes each attempt, paired with a CountDownLatch keyed by eventId. Probes belong only in tests or observability with clear semantics, never mixed up with business-committed event counts.

## 17. Testing the crash window after DB commit, before offset commit

This is the most critical scenario for at-least-once processing.

### Level 1: simulating a controllable boundary

You can set up the precondition via the service before sending the Kafka record:

~~~java
CreditEvent event = new CreditEvent(
        eventId, accountId, new BigDecimal("25.00"));

creditService.apply(event); // Simulate DB already committed before crash.

// Then publish the same event to Kafka as a redelivery.
kafkaTemplate.send("credit-events", accountId, json);
~~~

When the listener receives the message, it must see the existing marker and not credit the balance again. Wait for the listener to finish processing the record as in section 16, then assert the balance and marker.

**This simulates the post-crash state**, rather than actually killing a process. It proves the service is safe when the database has already recorded the event before an extra Kafka delivery arrives.

### Level 2: fault injection inside the listener

You can inject a failure **after creditService.apply returns**, but before the listener returns normally:

~~~java
public void onMessage(ConsumerRecord<String, String> record)
        throws Exception {

    CreditEvent event =
            mapper.readValue(record.value(), CreditEvent.class);

    creditService.apply(event); // DB transaction already committed.

    if (faultInjector.failAfterDatabaseCommit(event.eventId())) {
        throw new SimulatedCrashGapException(
                "Injected after DB commit");
    }
}
~~~

In the test, the fault injector fails **only once**, after which the error handler must redeliver the record. Assert the listener invocation count, marker count = 1, and that the balance increased only once.

This is also a **simulation**, not an actual JVM crash; Spring Kafka error-handler retries can have a different lifecycle from process restarts, though the idempotency behavior to prove is the same.

### Level 3: real crash/restart

With Testcontainers or an integration environment:

1. Run the consumer in a separate process/container.
2. Publish an event.
3. Use a controlled hook to pause right after the DB commits.
4. Kill the consumer process **before the Kafka offset commits**.
5. Restart the consumer with the same groupId and DB repository.
6. Wait for the record to be redelivered and finish processing.
7. Verify the balance increased once and the marker exists once.

Tests must synchronize explicitly to confirm **the DB committed and the offset did not commit**, never relying on `Thread.sleep` and killing at a guessed time. This is a heavy integration/failure test suited for scheduled runs or dedicated CI pipelines.

## 18. Testing a producer sending two records with the same eventId at different offsets

Two calls to **KafkaTemplate.send** with the same payload can produce two records at different offsets. The test in section 16 intentionally did this.

This differs from **same-offset redelivery**:

~~~text
Kafka partition 0:
  offset 100 -> eventId=credit-001
  offset 101 -> eventId=credit-001

Consumer receives offset 100: applies business logic.
Consumer receives offset 101: deduplicates, does not apply.
~~~

Producer idempotence does not necessarily prevent two intentional sends of the same business event, because two send calls are two valid records in the Kafka log. Business idempotency must rely on a **stable eventId or operationId**.

Have a dedicated test for the same eventId published via **two producer sends**, not merely seeking back to re-read one offset. If the system uses multiple topics representing the same event, align the dedup scope with the business contract.

## 19. Testing retries, DefaultErrorHandler, and DLT replay

Spring Kafka provides error-handling mechanisms such as **DefaultErrorHandler**, retry/backoff, and **DeadLetterPublishingRecoverer**. Idempotency tests must align with that policy.

Illustrative configuration:

~~~java
@Bean
DefaultErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> recovererTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(recovererTemplate);

    // Example: up to three retries per configured backoff.
    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 3L));

    // Unrecoverable payload errors normally should not
    // retry forever. Define an exception classification policy.
    return handler;
}
~~~

This snippet requires Spring Kafka, Apache Kafka client, and matching imports. **FixedBackOff(1_000L, 3L)** means three retries after the initial processing attempt with a one-second backoff, subject to the container handler lifecycle. Default DLT naming and target partitions depend on configuration/topics; ensure the DLT topic exists with valid partitions.

### Test cases

**Transient database errors**

- When an update hits timeout/deadlock, the transaction rolls back both the marker and the business effect.
- DefaultErrorHandler retries the record.
- Once the error clears, the service applies it exactly once.
- No marker is persisted while the transaction has not committed.

**Invalid payload errors**

- Unparseable JSON or missing eventId.
- Does not invoke the business service.
- Policy routes to DLT/quarantine or handles per contract.
- Never silently commits the offset if the record has not been properly recovered.

**Payload conflicts**

- EventId already processed, yet payload differs.
- Consumer reports a conflict; policy routes to DLT/audit or investigation.
- Previously written data remains unchanged.

**Replay from DLT**

- If the event was never applied, after fixing the root cause it can be applied once.
- If the event was already applied and gets re-driven, the marker prevents duplicate side effects.
- Re-drive must preserve the **original eventId/operationId**, never generating a new eventId unless business logic defines it as a genuinely new operation.

**A DLT is a mechanism for retaining and handling failed messages, not proof of idempotency.** If a record republished from a DLT gets a brand-new randomly generated key from a replay tool, eventId-based protections can be defeated.

## 20. Testing when offsets are reset, rebalanced, or restarted

A consumer group can re-read many records after offsets are reset or configuration/recovery changes. The goal is zero duplicate business effects.

Suggested scenarios:

| Scenario | Test action | Expectation |
| --- | --- | --- |
| Reset offset to an already-processed record | Seek/reset consumer in test environment | Balance does not increase again |
| Restart with same consumer group | Stop and restart consumer | Marker remains and output stays accurate |
| Rebalance between two instances | Add/remove consumer mid-processing | No lost or duplicate business effects |
| Replay on a new topic | Republish same eventId to replay topic with same-scope consumer | Not applied twice |
| Group ID changed | New consumer reads history | With same business scope, still deduplicates |
| Marker retention too short | Purge marker then replay old event | Test must surface the duplicate risk |

**GroupId and consumer_scope are not necessarily the same concept.** Group ID governs Kafka consumption; business consumer scope identifies which side effect was executed. If changing groupId to reprocess for the same side effect, keep the marker scope stable.

Never alter consumer group offsets in production just to run tests. Use isolated test topics/groups and control consumer stop timing when resetting.

## 21. Testing ordering and non-commutative business operations

Idempotency alone does not solve **out-of-order processing**.

Example of two valid events:

~~~text
E1: Set account status = ACTIVE, version 3
E2: Set account status = CLOSED, version 4

Consumer receives E2 then E1.
Different eventIds mean dedup does not stop E1 from overwriting E2.
~~~

If business logic requires keeping the latest state by version, add extra protection:

- Events carry **aggregateId** and **sequence/version**.
- Update target conditionally only when version increases.
- Manage ordering via Kafka keys and partitions where appropriate.
- Design explicit late-event handling.

For credit events, two amounts with distinct eventIds may sum to the same total in any order under normal conditions. Yet for **status updates, balance replacements, or workflow states**, order and version usually matter.

A reliable test suite separates:

- **Duplicate tests:** the same logical operation creates no duplicate effect.
- **Ordering/version tests:** newer events are never overwritten by older events.
- **Concurrency tests:** two workers updating an aggregate preserve invariants.
- **Reconciliation tests:** final totals match the source of truth.

## 22. Marker retention: testing replays outside the retention window

The `processed_event` table grows over time. If a processed event's marker is purged after 7 days and then re-driven on day 30, the consumer may treat it as a brand-new event.

~~~text
Day 1:  E1 applied, marker saved.
Day 7:  Cleanup deletes marker.
Day 30: DLT re-drives E1.
        No marker left -> credits a second time.   (WRONG)
~~~

Retention policies must align with the **maximum replay window** across Kafka topics, DLTs, backups, backfill processes, and business rules. Systems can retain markers long-term for financial events, or use a domain table holding a unique business operation ID independent of technical marker cleanup.

Retention tests should verify:

1. Markers are never purged while still inside the replay window.
2. If markers are archived, deduplication still catches duplicates via long-term storage or unique business keys.
3. Cleanup never deletes markers belonging to active transactions.
4. Historical backfills do not accidentally treat every event as new.

A Bloom filter or TTL Redis cache can cut database query volume, yet **never replaces an authoritative dedup store** when duplicate application is forbidden.

## 23. Observing duplicates and retries in production

Useful metrics:

| Metric | Meaning |
| --- | --- |
| **kafka_consumer_record_attempts_total** | Number of times listeners attempted to process records |
| **business_event_applied_total** | Number of new events applied |
| **business_event_duplicate_total** | Number of duplicate events detected |
| **business_event_payload_conflict_total** | Number of eventIds reused with differing payloads |
| **business_event_processing_failure_total** | Failures before completion |
| **kafka_consumer_lag** | Group consumption backlog |
| **kafka_dlt_records_total** | Records routed to DLT |
| **database_transaction_rollback_total** | Rollbacks related to processing |

Crucially, define **attempt** vs. **applied** clearly. A record retried 3 times generates 3 attempts but only 1 business application. Counting attempts as business throughput inflates dashboards.

Never put **eventId**, accountId, or UUIDs as permanent metric tags because they cause massive cardinality. Log **eventId, topic, partition, offset, and consumer scope** with data-protection controls, then use correlation IDs for investigation.

When duplicates spike, look for root causes:

- Producer resending events due to timeouts?
- Excessive consumer group rebalancing?
- Slow DB processing delaying polls/offset commits?
- Error handler continuously retrying?
- Operator re-driving a DLT?
- A client resending the same business request?

**Some duplicates are normal in an at-least-once architecture**, yet a sudden spike signals an operational issue.

## 24. Checklist of test cases to include in the suite

| # | Scenario | Minimum outcome to assert |
| ---: | --- | --- |
| 1 | Same eventId, same payload, call service twice | Balance increases once; marker = 1 |
| 2 | Two different eventIds, same account/amount | Balance increases twice |
| 3 | Same eventId, different amount | Conflict, no second update |
| 4 | Same eventId, different accountId | Conflict, does not credit another account |
| 5 | Failure after marker INSERT, before commit | Marker rolls back; retry succeeds |
| 6 | Two threads apply same event concurrently | One marker, one business effect |
| 7 | Two Kafka records at different offsets with same eventId | Wait for both to process; balance increases once |
| 8 | DB committed, offset uncommitted, then redelivery | Not credited a second time |
| 9 | Consumer restarts/rebalances and re-reads | Final data has no duplicates |
| 10 | DLT replays an already-applied record | No repeated side effect |
| 11 | DLT replays an unapplied event after fix | Applied exactly once |
| 12 | Bad JSON / missing eventId | Creates neither marker nor business effect |
| 13 | Valid events processed out-of-order | Does not break business versions/invariants |
| 14 | Two instances/processes consume duplicates | Database unique constraint holds |
| 15 | Marker retention then historical replay | Does not lose idempotency protection |
| 16 | Kafka or DB infrastructure failure | Never acks offset early before business commit |

For broker tests, observe **enough records processed** before asserting final data. For database tests, verify **real transactions and real unique constraints**, not merely mocked method returns.

## 25. Very common testing mistakes

### Sending duplicates and merely waiting with Thread.sleep

~~~java
kafkaTemplate.send(topic, key, payload);
kafkaTemplate.send(topic, key, payload);
Thread.sleep(2000L);

assertBalance(...);
~~~

Processing time varies with CPU, broker, network, rebalances, and CI. A fixed sleep can be too short or hide slow tests. Use **Awaitility**, CountDownLatches, or committed-offset/probe checks on observable conditions.

### Asserting too early after the first record

The balance is already right after one delivery while the second delivery has not run yet. The test passes falsely. Wait until both records have been processed/committed along the test path.

### Counting markers without checking balance

Marker = 1 can coexist with a wrong balance if markers commit independently of business effects. Always assert **both markers and side effects**.

### Checking balance without checking markers

The balance looks right temporarily, yet missing markers mean the next restart could credit twice. Assert durable markers.

### Using a mocked database to prove concurrency

Mocks do not reproduce PostgreSQL unique constraints, locks, and transactions. Race tests need a real DB.

### Putting `@Transactional` on the test method leaving fixtures uncommitted

Listeners/workers on other threads cannot see uncommitted fixtures, causing flaky tests or broken transaction models. Commit fixtures before triggering consumers.

### Generating a random eventId on every resend

Then it is no longer the same logical event. Duplicate tests must preserve a **fixed eventId** across sends.

### Deleting markers between two assertions

A test can accidentally wipe out its own dedup mechanism. Isolate via dedicated eventId/accountId values instead of truncating shared tables while consumers run.

### Testing only within a single JVM

A ConcurrentHashMap can "pass" in one JVM yet fail across multiple pods. Use durable unique constraints and cross-instance tests proportionate to criticality.

### Assuming producer idempotence suffices for the database

Producer idempotence and Kafka transactions do not automatically guarantee exactly-once for JDBC or external API effects. Tests must cover DB commits before Kafka offsets.

## 26. Practical implementation workflow

Apply these steps for a new consumer:

**Step 1 — Define the logical operation.** Lock down a stable eventId or business operationId across retries, republishes, and DLT replays.

**Step 2 — Identify protected side effects.** Such as crediting balances, creating invoices, sending emails, or calling partner APIs. Each side effect has its own transaction boundary.

**Step 3 — Pick a durable dedup store.** For PostgreSQL side effects, use a unique constraint on scope + event ID or appropriate business key.

**Step 4 — Tie marker and business effect in the same transaction.** Any failure before commit must roll back both.

**Step 5 — Let the listener finish after business commit.** Offset commit can follow; tolerate replays and let the service handle them idempotently.

**Step 6 — Write service tests first.** Cover duplicates, distinct IDs, payload conflicts, rollbacks, and concurrent inserts.

**Step 7 — Write Kafka integration tests.** Publish two Kafka records with the same eventId, wait for the consumer group to process both, and assert markers and data.

**Step 8 — Test the failure window.** Simulate DB commit before offset commit, then run real crash/restart tests in an appropriate environment.

**Step 9 — Test retries/DLTs and retention.** Re-drives must keep original event IDs, and markers must outlive replay windows.

**Step 10 — Monitor in production.** Track attempts/applied/duplicates/conflicts metrics, Kafka lag, and DB rollbacks; investigate abnormal spikes in duplicate rates.

## 27. Conclusion

A reliable Spring Kafka system **must never rely on the assumption that every event reaches a consumer strictly once**. Under at-least-once delivery, retries or crashes after DB commit and before offset commit are scenarios that must be designed for from day one.

The practice's solution uses a **stable eventId/operationId**, a **durable unique constraint**, and an **atomic transaction joining the dedup marker with the business update**. When the same event arrives a second time, the consumer verifies matching payload and skips the side effect; when two distinct events arrive, they process independently; when a transaction fails, both marker and effect roll back so retries can proceed.

The test suite must cover **sending the same event twice, redeliveries, payload conflicts, rollbacks, race conditions, DLT replays, and restarts**. A good test verifies not merely that the Kafka listener was invoked, but **the exact number of committed business effects** and that **valid events are never mistakenly dropped**. That is the practical meaning of **testing duplicates and idempotency** in Spring Kafka operations.

