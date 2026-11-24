# Testing Sending, Receiving, and Duplicate Message Handling with Spring Boot

## 1. Real-world scenario and lesson goals

A service consumes `OrderCreated` events from Apache Kafka. Each event grants reward points to an order. A producer publishes events to the broker; a `@KafkaListener` consumes each event, updates the `order_points` table, and records history in the `processed_message` table.

If either producer or consumer hits a network blip and resends the same event, Kafka can deliver **two records with the same business message ID**. The two records may carry different Kafka offsets while representing the same business request. If the listener blindly adds points on every delivery, the customer gets double-credited. Therefore we must test **the full send → broker → listener → database flow**, as well as **idempotency**: reprocessing the same message must produce no additional business effect.

This is an integration practice lesson (*parent group: Integration Practice*) in the **Spring Boot – testing** module. The goal is not merely mocking `KafkaTemplate.send()` to check a method call: we need a real test broker and a real listener receiving records asynchronously.

**After this lesson, you will be able to:**

1. Distinguish successful send to the broker, delivery to the listener, DB transaction commit, and consumer offset commit.
2. Write integration tests using **Spring Boot 3.3.5, Java 17, Spring Kafka 3.2.x, JUnit Jupiter, and `@EmbeddedKafka`**, without Docker.
3. Send JSON events via `KafkaTemplate`, inspect `SendResult`/`RecordMetadata`, and await listener completion with **Awaitility** instead of `Thread.sleep`.
4. Pick a clear **business `messageId`** rather than using the `Kafka offset` as an idempotency key.
5. Understand Kafka producer keys by `orderId` and per-partition ordering semantics.
6. Enforce `PRIMARY KEY(message_id)` on the inbox table to prevent duplicate processing **even across multiple consumer instances**.
7. Place **INSERT inbox + UPDATE business state inside the same JDBC transaction**, avoiding race-prone check-then-act `SELECT` followed by `INSERT`.
8. Distinguish `DuplicateKeyException` (recognized as a duplicate) from data, network, code, or other SQL errors **that must be retried or investigated**, never swallowed indiscriminately.
9. Reject treating the same `messageId` with a **different payload** as a valid redelivery; detect collisions and route them to error handling.
10. Build a runnable project with **12 JUnit Jupiter `@Test` methods**, testing sending, receiving, two/three redeliveries, two event IDs on one order, two independent orders, offsets, transaction rollback, payload collision, and validation.
11. Grasp **at-least-once vs exactly-once**: a DB unique constraint ensures DB business effects happen at most once per message ID, without turning emails, HTTP calls, Kafka, and DB into a single atomic transaction.
12. Plan extensions for retry/backoff, dead-letter topics, poison messages, schema evolution, Testcontainers, observability, and CI.
13. Understand why `@Transactional` on the test thread does not roll back a listener running on a Kafka consumer thread.
14. Reduce flaky tests using dedicated topics/groups, UUID-scoped data, DB-backed awaits, and clean broker shutdown lifecycles.

**Fixed stack:** Java 17, **Spring Boot 3.3.5**, Spring Kafka managed by the Spring Boot 3.3.x BOM, JUnit Jupiter, in-memory H2, and `spring-kafka-test`. APIs belong to Spring Kafka 3.2: `KafkaTemplate.send` returning `CompletableFuture`, `@EmbeddedKafka(... bootstrapServersProperty=..., kraft=true)`, `@KafkaListener`, JSON serializer/deserializer, and `AckMode.RECORD`. Snippets labeled “illustrative” are not standalone files; all files in the project tree in Sections 7–11 form the complete program.

## 2. Guarantees: sending, receiving, processing, committing

To avoid asserting the wrong milestone, separate four checkpoints:

| Milestone | Observed in this lesson | Proves business effect? |
|---|---|---|
| **Producer sends** | `KafkaTemplate.send(...)` returns a `CompletableFuture` | **No**: asynchronous send can still fail |
| **Broker acknowledges write** | `future.get(timeout)` returns `SendResult` with topic/partition/offset | **No**: consumer may not have read it yet |
| **Listener updates DB** | `@KafkaListener` calls service; JDBC transaction commits | **Yes**, for committed DB changes |
| **Consumer offset committed** | Container `AckMode.RECORD` commits after normal listener return | Does not mean DB and offset share one atomic transaction |

**A possible execution timeline:**

~~~text
Producer                Kafka broker             Listener                 H2 / SQL
   |                          |                      |                       |
   | send OrderCreated(id=A)  |                      |                       |
   |------------------------->|                      |                       |
   |    SendResult(topic,     |                      |                       |
   |      partition, offset)  |                      |                       |
   |<-------------------------|                      |                       |
   |                          |   deliver record A   |                       |
   |                          |--------------------->| INSERT processed A    |
   |                          |                      | UPDATE order points   |
   |                          |                      |---------------------->|
   |                          |                      |      COMMIT OK        |
   |                          |                      |<----------------------|
   |                          |                      | listener returns      |
   |                          |<---------------------| container commits offset
~~~

**Core risk:** If the DB commits and the process crashes **before the offset commits**, record A can be redelivered after restart or rebalance. That is why idempotency must live in consumer/business persistence, **not solely on the producer**.

A test asserting `future.get()` succeeded **has not tested consumption**. A test verifying a Mockito mock of the listener **has not tested broker serialization or DB side effects**. This lesson tests multiple milestones with a real embedded broker and SQL.

### 2.1. At-most-once, at-least-once, and exactly-once

- **At-most-once**: messages may be lost under failure, never processed twice under the delivery pattern.
- **At-least-once**: messages may be redelivered, so consumers **must tolerate duplicates**.
- **Exactly-once processing** has a narrow scope within Kafka transactional producers and stream processing; it does not automatically span external PostgreSQL, HTTP APIs, email, or payment systems in one transaction.
- **Idempotent business effect**: repeated deliveries with the same business key produce the effect of one delivery—for instance, one `processed_message.message_id` grants points only once.

In this lesson we prove **DB update idempotency** per message ID via a `PRIMARY KEY` and transaction. We do not claim distributed end-to-end exactly-once across external systems. Two Kafka records exist at two offsets, yet produce **one receipt** and **one points grant**.

### 2.2. Why is `messageId` not the Kafka offset?

A Kafka offset identifies a record's position **within a topic partition**. A producer re-sending the same event with a new `send()` call creates a new offset. Deduplicating by offset treats the redelivery as a brand-new event.

**Business `messageId`** is a UUID/ULID or source event identifier. Rules:

- Keep `messageId` unchanged when **retrying the same event**.
- Generate a **new `messageId`** for a new business action/event, even if it targets **the same `orderId`**.
- Never mutate the payload for an already-emitted ID. Same `messageId` with different `orderId/points` is a **collision/contract violation**.
- Scope idempotency keys broadly enough: use `(consumer_name, message_id)` or `(event_type, message_id)` in production if multiple independent consumer groups process the same event ID.
- Never use `orderId` as the deduplication key if one order legitimately receives multiple **distinct events**.

## 3. Distinguishing four easily confused IDs/keys

| Concept | Example | Purpose |
|---|---|---|
| Business `messageId` | `event-7c...` | Deduplicate processing by business event |
| Business `orderId` | `order-1a...` | Aggregate being updated and Kafka record key here |
| Kafka key | `order-1a...` | Same key is normally routed by partitioner to the same partition to preserve per-key order |
| Kafka topic/partition/offset | `orders.created.v1/0/42` | Broker record location, not a semantic idempotency ID |

Tests here configure **one partition** for easier observation. Production topics often have many partitions; with a stable key, records for the same order normally land in the same partition, yet **Kafka does not guarantee global ordering across topics, partitions, or consumer groups**. Deduplication **must never rely solely on partition ordering**.

### 3.1. Producer idempotence vs consumer idempotence

Kafka producers support `enable.idempotence=true` to handle **producer batch retries** by producer ID and sequence number, eliminating one class of protocol-level duplicates. However, if application code actively calls `send(event)` **twice**, those are two distinct sends with two sequence numbers; Kafka **stores both records**. Producer idempotence has no knowledge that `messageId` inside both JSON payloads is identical.

The consumer inbox `PRIMARY KEY(message_id)` solves **business duplicates** once records reach the listener. The two mechanisms complement rather than replace each other.

## 4. Designing an idempotent consumer

**Wrong: SELECT first, then INSERT/UPDATE later without locking:**

~~~java
// Illustrative anti-pattern; not part of the runnable project.
// Two consumer instances can both observe exists=false.
if (!repository.existsByMessageId(event.messageId())) {
    repository.updateBusinessState(event);
    repository.saveReceipt(event.messageId());
}
~~~

Race:

~~~text
Consumer A: SELECT processed(A) -> not found
Consumer B: SELECT processed(A) -> not found
Consumer A: UPDATE + INSERT
Consumer B: UPDATE + INSERT   (effect applied twice)
~~~

**Better:** let the database **enforce a unique key** and place **recording the processed receipt plus the business update inside a single transaction**. Insert-first flow:

~~~text
BEGIN TRANSACTION
  INSERT INTO processed_message(message_id,...)
  UPDATE order_points SET total_points=total_points+?
COMMIT

If INSERT hits duplicate PK:
  transaction fails/rolls back
  never runs UPDATE order_points
  read committed receipt to check payload really matches
  same payload -> no-op, return normally from listener
  different payload -> throw, error handling required
~~~

`@Transactional` works only if invoked through a **Spring proxy**, the transaction spans the real SQL statements, and the DB supports transactions. The project separates `OrderInboxService` into its own Spring `@Service`; the listener calls it via DI so the transaction interceptor runs. **Never catch `DuplicateKeyException` inside the transactional method and keep issuing updates**: on PostgreSQL, an SQL error marks the transaction aborted; catching **outside the proxy** after rollback is cleaner.

**Pattern limitation:** If the service sends an email or payment HTTP request **between** inserting the receipt and `COMMIT`, those actions do not roll back with the DB. For external side effects, use a **transactional outbox**, downstream idempotency keys, and dedicated retry policies.

## 5. Choosing the right testing strategy

**A solid suite covers these layers:**

1. **Contract/unit tests**: Java record validation, ID mapping, pure business logic; no broker needed.
2. **Repository/transaction tests**: duplicate key, rollback, missing order; real SQL on H2 or target DB.
3. **Messaging integration tests**: `KafkaTemplate.send`, JSON serialization/deserialization, real listener, real DB, duplicates, and async completion.
4. **Infrastructure tests with real containers**: production-like PostgreSQL/Kafka, broker restarts, consumer rebalances, DLT, retries, network faults, security (SASL/TLS).
5. **End-to-end tests**: multi-service flows, outbox/inbox, downstream side effects/compensation.

This lesson focuses on layer **3** and the transactional portion of layer **2**. The embedded broker (`spring-kafka-test`) needs no Docker, yet does not replace compatibility tests against a managed Kafka cluster; likewise, H2 does not mirror all PostgreSQL transaction/error semantics.

### 5.1. Why not test using `Thread.sleep(500)`?

`@KafkaListener` runs on a consumer thread whose scheduling depends on startup, partition assignment, CPU, and GC. Fixed sleeps are both slow and flaky. Use:

~~~java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> assertEquals(1, jdbcCount()));
~~~

**Illustrative snippet**: requires `org.awaitility.Awaitility.await`, Java `Duration`, and a test-defined `jdbcCount()`. Awaitility polls assertions until they pass or hit a finite timeout. In the sample project, tests wait on the listener's **post-DB-commit audit**, then inspect SQL state. Never wait only on a Mockito invocation if you need to prove the business update committed.

### 5.2. Testing duplicates without deliberately crashing the broker

Publishing **two or three Kafka records with the same `messageId`** is a **deterministic** way to test idempotency when the consumer receives duplicate records. It **does not by itself prove** Kafka redelivery behavior after consumer crashes, rebalances, or failed offset commits; those scenarios require dedicated fault-injection/chaos integration tests. State the scope of proof accurately.

## 6. Designing the runnable project

**Project:** Gradle, Spring Boot 3.3.5, Java 17, Spring Kafka, Spring JDBC, H2, Spring Kafka Test, and JUnit Jupiter/Awaitility.

**Actual flow:**

~~~text
JUnit test:
  create order_points(orderId,0)
  publisher.publish(new OrderCreatedEvent(messageId,orderId,points))
        |
        v
  KafkaTemplate<String,OrderCreatedEvent>
        |
        v
  @EmbeddedKafka broker: orders.created.v1
        |
        v
  @KafkaListener OrderMessageListener
        |
        v
  OrderInboxService.processOnce(event)  <-- @Transactional
        |
        +-- INSERT processed_message UNIQUE(message_id)
        +-- UPDATE order_points += points
        +-- COMMIT
        |
        +-- on duplicate PK -> rollback, compare stored receipt
        |        +-- same payload -> audit duplicate, return normally
        |        +-- different payload -> throw, error handling required
        |
        v
  DeliveryAudit (test observation only)
        |
        v
  Awaitility waits; JUnit checks persisted state
~~~

**Distinguishing test instrumentation:** `DeliveryAudit` below is an in-memory Spring bean counting how many times the listener finished each message ID, letting tests await two or three deliveries. In production, replace it with bounded Micrometer counters/traces or test-only instrumentation rather than keeping **every messageId forever** in a `ConcurrentHashMap` and leaking memory. **The database inbox is the source of truth**; the audit merely observes async completion.

### 6.1. Complete directory tree

~~~text
settings.gradle
build.gradle
src/main/java/demo/messaging/MessagingApplication.java
src/main/java/demo/messaging/OrderTopics.java
src/main/java/demo/messaging/OrderCreatedEvent.java
src/main/java/demo/messaging/OrderEventPublisher.java
src/main/java/demo/messaging/OrderInboxService.java
src/main/java/demo/messaging/OrderMessageListener.java
src/main/java/demo/messaging/DeliveryAudit.java
src/test/resources/application.properties
src/test/resources/schema.sql
src/test/resources/junit-platform.properties
src/test/java/demo/messaging/MessagingIntegrationTest.java
~~~

No `@Configuration` in test sources is accidentally picked up by `@SpringBootApplication` scanning; every Java class under `main` has a clear role. DB schema lives solely in `src/test/resources/schema.sql`, preventing demo SQL from running under production profiles.

## 7. Gradle and test broker/DB configuration

**settings.gradle**

~~~groovy
rootProject.name = 'messaging-idempotency-integration-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.kafka:spring-kafka'

    // H2 runs integration tests without an external DB.
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Single JVM: avoid multiple embedded brokers sharing
    // system properties/ports in this example.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Why `runtimeOnly h2` instead of `testImplementation h2`?** H2 is needed by the Spring Boot application context **when running tests**, and Gradle's runtime classpath is included in the test runtime classpath. For a real app using PostgreSQL in production, placing H2 in `testRuntimeOnly 'com.h2database:h2'` is a clean choice when runtime already has its own DB driver. This demo boots the app solely through `SpringBootTest` and does not run in production.

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Parallel JUnit execution is disabled so broker lifecycle, SQL fixture setup, and test observations do not interfere in this lesson. This is not a blanket rule for every suite; tests with isolated resources can run concurrently. When raising Gradle `maxParallelForks` or running modules in parallel, **each JVM has a separate Spring TestContext cache** and in-JVM resource locks do not span JVMs.

### 7.1. Test-only configuration

**src/test/resources/application.properties**

~~~properties
spring.main.banner-mode=off

# SQL/H2 only in tests. Schema is in src/test/resources/schema.sql.
spring.datasource.url=jdbc:h2:mem:message_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Producer JSON. Disable Java type headers to reduce class-name coupling.
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer
spring.kafka.producer.acks=all
spring.kafka.producer.properties.enable.idempotence=true
spring.kafka.producer.properties.spring.json.add.type.headers=false

# Consumer JSON. Accept only package demo.messaging in this lesson.
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties.spring.json.use.type.headers=false
spring.kafka.consumer.properties.spring.json.value.default.type=demo.messaging.OrderCreatedEvent
spring.kafka.consumer.properties.spring.json.trusted.packages=demo.messaging
spring.kafka.consumer.group-id=order-inbox-demo-group
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false

# Container commits offset after listener returns normally.
spring.kafka.listener.ack-mode=record
spring.kafka.listener.missing-topics-fatal=true
~~~

**Note on `spring.kafka.bootstrap-servers`:** the file **does not hard-code `localhost:9092`**. `@EmbeddedKafka(bootstrapServersProperty="spring.kafka.bootstrap-servers")` on the integration test maps the dynamically chosen localhost broker port into Boot's property using `spring-kafka-test`. Never confuse the Kafka broker address with the H2 datasource URL.

**Why `spring.json.use.type.headers=false` and `value.default.type`?** The producer omits Java type metadata headers, and the consumer deserializes directly into `demo.messaging.OrderCreatedEvent`. That keeps the demo JSON clean, though production systems should adopt **schema contracts/versioning** (Avro/Protobuf/JSON Schema) and a schema registry/mapping instead of assuming one class for every event.

**`AckMode.RECORD`**: when `enable-auto-commit=false` and Kafka transactions are disabled, the container commits the offset after the listener succeeds on each record. An exception thrown by the listener routes to the error handler and **is not immediately treated as processed**. This lab configures no DLT; in production, poison messages require retry/recoverer configuration.

### 7.2. Test SQL schema

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE order_points (
    order_id VARCHAR(100) PRIMARY KEY,
    total_points INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE processed_message (
    message_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    points INTEGER NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
~~~

Intentionally separates the **business state table** and the **inbox table**. Unique `message_id` enforces deduplication at the database level rather than a Java `ConcurrentHashMap`. The business update and receipt insert run inside **one transaction**. A repeated message ID never updates `order_points` a second time.

**H2 caveat:** H2 is convenient locally yet differs from PostgreSQL in locking, isolation, SQLState, and transaction behavior. Before going to production, run integration tests against **PostgreSQL Testcontainers** and real migrations. Never rely on an in-memory inbox if deduplication must survive process restarts.

## 8. Main Java sources: application, event, and publisher

### 8.1. Main application

**src/main/java/demo/messaging/MessagingApplication.java**

~~~java
package demo.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;

@SpringBootApplication
@EnableKafka
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

`@EnableKafka` explicitly enables `@KafkaListener`-annotated endpoints. Spring Boot auto-configures `KafkaTemplate`, the listener container factory, and supporting beans when dependencies and properties are present. No embedded HTTP server runs because `spring-boot-starter-web` is absent; tests use `WebEnvironment.NONE`.

### 8.2. Shared topic constant

**src/main/java/demo/messaging/OrderTopics.java**

~~~java
package demo.messaging;

public final class OrderTopics {

    public static final String CREATED = "orders.created.v1";

    private OrderTopics() {
    }
}
~~~

Producer, consumer, and `@EmbeddedKafka` share the **same constant**, avoiding typos like `orders.create.v1` vs `orders.created.v1`. The `v1` suffix is an illustrative contract namespace; publishing a new schema requires its own compatibility/versioning policy.

### 8.3. Event contract Java record

**src/main/java/demo/messaging/OrderCreatedEvent.java**

~~~java
package demo.messaging;

public record OrderCreatedEvent(
        String messageId,
        String orderId,
        int points) {

    public OrderCreatedEvent {
        if (messageId == null || messageId.isBlank()) {
            throw new IllegalArgumentException(
                    "messageId must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (points <= 0) {
            throw new IllegalArgumentException(
                    "points must be positive");
        }
    }
}
~~~

Java 17 records work seamlessly with Jackson in Spring Kafka 3.2 / Boot 3.3. `messageId` stays **constant** across retries of the same semantic event; `orderId` is the aggregate ID used as the Kafka record key; `points` is the business amount. Canonical constructor validation guards both Java-constructed events and deserialized JSON; deserialization failures occurring before the listener need a dedicated error handler in production.

**Do not treat a `record` as a schema registry.** Renaming `points`, removing a field, or changing types can break downstream consumers even when the producer compiles. Add contract/schema tests when multiple services integrate.

### 8.4. Real producer

**src/main/java/demo/messaging/OrderEventPublisher.java**

~~~java
package demo.messaging;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafka;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafka) {
        this.kafka = kafka;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>>
            publish(OrderCreatedEvent event) {

        // orderId is the Kafka key: keeps records for an order
        // in the same partition when partition config is stable.
        return kafka.send(
                OrderTopics.CREATED, event.orderId(), event);
    }
}
~~~

`KafkaTemplate.send` returns `CompletableFuture<SendResult<...>>`; production producers need not block with `.get()`. **Tests** may wait with a finite timeout to confirm the broker acknowledged the record. `SendResult` provides `RecordMetadata.topic()`, `partition()`, and `offset()`.

**Never treat a successful send as proof of the business effect.** Future completion proves only producer acknowledgment per `acks` config, not that the listener has finished its database transaction.

## 9. Inbox service and listener: atomic DB effect and duplicate detection

### 9.1. Transactional service

**src/main/java/demo/messaging/OrderInboxService.java**

~~~java
package demo.messaging;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderInboxService {

    private final JdbcTemplate jdbc;

    public OrderInboxService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void processOnce(OrderCreatedEvent event) {
        // DB unique constraint is the arbiter across
        // consumer instances (not a Java if-check).
        jdbc.update(
                "INSERT INTO processed_message "
                        + "(message_id, order_id, points) "
                        + "VALUES (?, ?, ?)",
                event.messageId(),
                event.orderId(),
                event.points());

        // Business mutation runs in the SAME JDBC transaction.
        int updated = jdbc.update(
                "UPDATE order_points "
                        + "SET total_points = total_points + ? "
                        + "WHERE order_id = ?",
                event.points(), event.orderId());

        if (updated != 1) {
            throw new IllegalArgumentException(
                    "Unknown orderId: " + event.orderId());
        }
    }

    public boolean matchesStoredReceipt(OrderCreatedEvent event) {
        // Called AFTER the duplicate transaction has rolled back.
        List<OrderCreatedEvent> stored = jdbc.query(
                "SELECT message_id, order_id, points "
                        + "FROM processed_message WHERE message_id = ?",
                (rs, rowNum) -> new OrderCreatedEvent(
                        rs.getString("message_id"),
                        rs.getString("order_id"),
                        rs.getInt("points")),
                event.messageId());

        return stored.size() == 1 && stored.get(0).equals(event);
    }
}
~~~

**Semantics to understand:**

- `INSERT` into `processed_message` happens before the business `UPDATE`.
- `PRIMARY KEY(message_id)` makes duplicates with the same ID **fail right on INSERT**, never reaching UPDATE.
- `@Transactional` sits on a Spring-managed service invoked by another bean (the listener), so the transactional proxy wraps both SQL statements.
- If `orderId` is missing, UPDATE returns 0; `IllegalArgumentException` rolls back the transaction, **removing the uncommitted inbox receipt**. That event is not falsely marked as processed.
- `matchesStoredReceipt` compares stored contents so **same ID with different payload** is never silently skipped. It executes as an independent SQL read after the failed transaction rolls back. On PostgreSQL, avoid the trap of querying inside the already-aborted transaction.
- If multiple logical consumer roles exist, include `consumer_name`/scope in the primary key. This illustrative example has **one** consumer subscriber and one event type.

**Warning:** This is a transactional inbox **within one DB**. If `processOnce` also publishes another event, calls an external API, or sends an email, add an outbox/downstream idempotency key; DB rollback will not undo a sent email.

### 9.2. Instrumentation for integration tests

**src/main/java/demo/messaging/DeliveryAudit.java**

~~~java
package demo.messaging;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class DeliveryAudit {

    private final ConcurrentMap<String, AtomicInteger> seen =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> duplicates =
            new ConcurrentHashMap<>();

    private static void increment(
            ConcurrentMap<String, AtomicInteger> map, String id) {

        map.computeIfAbsent(id, key -> new AtomicInteger())
                .incrementAndGet();
    }

    public void applied(String messageId) {
        increment(seen, messageId);
    }

    public void duplicate(String messageId) {
        increment(seen, messageId);
        increment(duplicates, messageId);
    }

    public int observed(String messageId) {
        AtomicInteger counter = seen.get(messageId);
        return counter == null ? 0 : counter.get();
    }

    public int duplicateCount(String messageId) {
        AtomicInteger counter = duplicates.get(messageId);
        return counter == null ? 0 : counter.get();
    }
}
~~~

No `Thread.sleep`, `synchronized` on test instances, or static global counters. Because event IDs use fresh UUIDs per test, observations never collide. This is a **demo/test audit**; production must not keep an unbounded map of every ID forever. Switch to Micrometer counters/structured logs/trace IDs or place the bean under test configuration if a real app has multiple consumers.

### 9.3. Real Kafka listener

**src/main/java/demo/messaging/OrderMessageListener.java**

~~~java
package demo.messaging;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    private final OrderInboxService inbox;
    private final DeliveryAudit audit;

    public OrderMessageListener(
            OrderInboxService inbox,
            DeliveryAudit audit) {

        this.inbox = inbox;
        this.audit = audit;
    }

    @KafkaListener(topics = OrderTopics.CREATED)
    public void on(OrderCreatedEvent event) {
        try {
            inbox.processOnce(event);
            // processOnce returns after the transaction commits.
            audit.applied(event.messageId());
        } catch (DuplicateKeyException duplicate) {
            // Exception exited the transactional proxy;
            // the transactional interceptor already rolled back.
            if (!inbox.matchesStoredReceipt(event)) {
                throw new IllegalStateException(
                        "messageId reused with different payload",
                        duplicate);
            }

            // Valid duplicate: no-op, let listener return normally.
            audit.duplicate(event.messageId());
        }
    }
}
~~~

**Why catch only `DuplicateKeyException`?** An inbox duplicate key is the **expected** case when the same message is redelivered. If the DB is unavailable, an `IllegalArgumentException` occurs for a missing order, deserialization fails, code has a bug, or a receipt payload conflicts, the listener **must never swallow the error and commit the offset as successful**. Those failures require configured retry/backoff/DLT/alerting; the demo project does not send poison messages through Kafka since no DLT pipeline is configured.

**Why is `audit.applied` placed after `processOnce`?** The `@Transactional` method returns only after the transaction interceptor commits (in normal synchronous JDBC configs). That gives tests a solid basis to wait for `audit.observed` before inspecting the DB. Still, `audit.applied` runs **before the container commits the Kafka offset**, so observed counts do not prove the broker offset was committed. That distinguishes the delivery layers.

**When a message ID collides with a different payload**, `matchesStoredReceipt` returns false and the listener throws rather than treating the collision as a valid retry. In production, DLT/alert/operator handling is needed so one poison record does not block the partition indefinitely.

## 10. Integration test class with 12 JUnit Jupiter methods

**src/test/java/demo/messaging/MessagingIntegrationTest.java**

~~~java
package demo.messaging;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@EmbeddedKafka(
        topics = OrderTopics.CREATED,
        partitions = 1,
        kraft = true,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MessagingIntegrationTest {

    @Autowired
    OrderEventPublisher publisher;

    @Autowired
    OrderInboxService inbox;

    @Autowired
    DeliveryAudit audit;

    @Autowired
    JdbcTemplate jdbc;

    private String newOrder() {
        String orderId = "order-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO order_points "
                        + "(order_id, total_points) VALUES (?, 0)",
                orderId);

        return orderId;
    }

    private OrderCreatedEvent event(String orderId, int points) {
        return new OrderCreatedEvent(
                "evt-" + UUID.randomUUID(), orderId, points);
    }

    private SendResult<String, OrderCreatedEvent> send(
            OrderCreatedEvent event) throws Exception {

        // Wait for broker acknowledgment, NOT consumer completion.
        return publisher.publish(event)
                .get(20, TimeUnit.SECONDS);
    }

    private void awaitObserved(String messageId, int atLeast) {
        await().atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                        assertTrue(
                                audit.observed(messageId) >= atLeast));
    }

    private int points(String orderId) {
        return jdbc.queryForObject(
                "SELECT total_points FROM order_points "
                        + "WHERE order_id = ?",
                Integer.class,
                orderId);
    }

    private int receiptCount(String messageId) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_message "
                        + "WHERE message_id = ?",
                Integer.class, messageId);
    }

    @Test
    void sendReturnsTopicPartitionAndOffset() throws Exception {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 7);

        RecordMetadata meta = send(e).getRecordMetadata();

        assertEquals(OrderTopics.CREATED, meta.topic());
        assertEquals(0, meta.partition());
        assertTrue(meta.offset() >= 0);

        awaitObserved(e.messageId(), 1);
        assertEquals(7, points(orderId));
    }

    @Test
    void consumerWritesReceiptAndUpdatesOrder() throws Exception {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 9);

        send(e);
        awaitObserved(e.messageId(), 1);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(9, points(orderId));
        assertEquals(0, audit.duplicateCount(e.messageId()));
    }

    @Test
    void sameMessageTwiceAppliesBusinessEffectOnlyOnce()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 11);

        send(e);
        send(e);
        awaitObserved(e.messageId(), 2);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(11, points(orderId));
        assertTrue(audit.duplicateCount(e.messageId()) >= 1);
    }

    @Test
    void sameMessageThreeTimesStillAppliesOnlyOnce()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 13);

        send(e);
        send(e);
        send(e);
        awaitObserved(e.messageId(), 3);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(13, points(orderId));
        assertTrue(audit.duplicateCount(e.messageId()) >= 2);
    }

    @Test
    void differentMessageIdsOnSameOrderBothCount()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent first = event(orderId, 4);
        OrderCreatedEvent second = event(orderId, 6);

        send(first);
        send(second);
        awaitObserved(first.messageId(), 1);
        awaitObserved(second.messageId(), 1);

        assertEquals(4 + 6, points(orderId));
        assertEquals(1, receiptCount(first.messageId()));
        assertEquals(1, receiptCount(second.messageId()));
    }

    @Test
    void eventsForDifferentOrdersDoNotInterfere()
            throws Exception {

        String orderA = newOrder();
        String orderB = newOrder();
        OrderCreatedEvent eventA = event(orderA, 3);
        OrderCreatedEvent eventB = event(orderB, 17);

        send(eventA);
        send(eventB);
        awaitObserved(eventA.messageId(), 1);
        awaitObserved(eventB.messageId(), 1);

        assertEquals(3, points(orderA));
        assertEquals(17, points(orderB));
    }

    @Test
    void sameMessageIdAtTwoOffsetsIsStillOneBusinessEvent()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 5);

        RecordMetadata first = send(e).getRecordMetadata();
        RecordMetadata second = send(e).getRecordMetadata();

        assertEquals(first.partition(), second.partition());
        assertTrue(second.offset() > first.offset());

        awaitObserved(e.messageId(), 2);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(5, points(orderId));
    }

    @Test
    void missingOrderRollsBackReceiptAndBusinessUpdate() {
        String unknown = "missing-" + UUID.randomUUID();
        OrderCreatedEvent e = event(unknown, 10);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> inbox.processOnce(e));

        assertTrue(error.getMessage().contains("Unknown orderId"));
        assertEquals(0, receiptCount(e.messageId()));

        // Do not send a poison record into Kafka in this test.
        // Test transaction rollback directly through the Spring proxy.
    }

    @Test
    void directDuplicateIsRejectedByUniqueConstraint() {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 8);

        inbox.processOnce(e);

        assertThrows(
                DuplicateKeyException.class,
                () -> inbox.processOnce(e));

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(8, points(orderId));
        assertTrue(inbox.matchesStoredReceipt(e));
    }

    @Test
    void sameIdWithDifferentPayloadIsRecognizedAsCollision() {
        String orderId = newOrder();
        OrderCreatedEvent original = event(orderId, 6);
        OrderCreatedEvent conflicting = new OrderCreatedEvent(
                original.messageId(), orderId, 999);

        inbox.processOnce(original);

        assertTrue(inbox.matchesStoredReceipt(original));
        assertFalse(inbox.matchesStoredReceipt(conflicting));
        assertEquals(6, points(orderId));

        // Do not send the conflicting event through Kafka:
        // a DLT/recovery policy is needed before testing poison flows.
    }

    @Test
    void invalidEventConstructionIsRejected() {
        String orderId = newOrder();

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent(null, orderId, 2));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent(" ", orderId, 2));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent("evt-valid", "", 2));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent("evt-valid", orderId, 0));
    }

    @Test
    void storedReceiptPreservesOriginalPayload() throws Exception {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 23);

        send(e);
        awaitObserved(e.messageId(), 1);

        Map<String, Object> stored = jdbc.queryForMap(
                "SELECT message_id, order_id, points "
                        + "FROM processed_message WHERE message_id = ?",
                e.messageId());

        assertEquals(e.messageId(), stored.get("MESSAGE_ID"));
        assertEquals(orderId, stored.get("ORDER_ID"));
        assertEquals(23, ((Number) stored.get("POINTS")).intValue());
        assertEquals(23, points(orderId));
    }
}
~~~

### 10.1. Exact count of 12 JUnit tests

| `@Test` method | Primary assertion |
|---|---|
| `sendReturnsTopicPartitionAndOffset` | Broker ACK has metadata; listener and DB finish afterward |
| `consumerWritesReceiptAndUpdatesOrder` | One message consumed → one inbox row, one business effect |
| `sameMessageTwiceAppliesBusinessEffectOnlyOnce` | Same ID sent twice → 1 effect, 1 duplicate |
| `sameMessageThreeTimesStillAppliesOnlyOnce` | Sent 3 times → 1 effect, at least 2 duplicates |
| `differentMessageIdsOnSameOrderBothCount` | Same order with two event IDs → both applied |
| `eventsForDifferentOrdersDoNotInterfere` | Two separate order IDs stay isolated |
| `sameMessageIdAtTwoOffsetsIsStillOneBusinessEvent` | Distinct Kafka offsets do not break business deduplication |
| `missingOrderRollsBackReceiptAndBusinessUpdate` | `UPDATE=0` → rolls back inbox insert too |
| `directDuplicateIsRejectedByUniqueConstraint` | DB PK directly prevents duplicate without double update |
| `sameIdWithDifferentPayloadIsRecognizedAsCollision` | Same ID with differing payload detected as mismatch |
| `invalidEventConstructionIsRejected` | Event contract rejects blank IDs / non-positive points |
| `storedReceiptPreservesOriginalPayload` | Inbox preserves exact id/orderId/points after consume |
| **Total** | **12 JUnit Jupiter methods** |

**Why don't assertions rely on test order?** Every test generates fresh UUIDs for `orderId` and `messageId`; `@BeforeEach` never executes `DELETE FROM ...` that might wipe rows still being processed by a prior test's listener. `junit-platform.properties` disables parallelism; sends await broker ACK and then await listener audit. If you still want separate DB state per test, use per-test schemas/namespaces rather than truncating shared tables while consumers are active.

**Why do several tests assert `audit.observed(id) >= n` instead of `== n`?** Kafka provides at-least-once delivery; if an unexpected redelivery occurs, total deliveries can exceed intentional sends. The business invariant remains **one receipt and one effect per business ID**. If you need to assert exact retry counts, isolate the retry policy and measure delivery attempts in test-specific state instead of conflating it with idempotency.

### 10.2. A note on `@DirtiesContext`

`@DirtiesContext(classMode=AFTER_CLASS)` closes the test context once the whole class finishes so the embedded broker and context-managed test resources are released. It is **not** placed on individual methods, avoiding restarting Kafka and the DB for every test. Never use `@DirtiesContext` merely to clear inbox rows; every test already uses unique IDs.

When multiple test classes use `@EmbeddedKafka` and share the Spring cached context, define topic/broker ownership and profile keys clearly. Never sprinkle `@DirtiesContext` everywhere or run those classes in parallel so class A shuts down the broker while class B is still using it.

## 11. Running Gradle and interpreting output

Running the project requires JDK 17 and a Gradle version compatible with Spring Boot 3.3.5, plus access to Maven Central on first build. Embedded Kafka requires CPU/RAM, temporary directories, and local loopback ports; **no Docker is required**. In CI sandboxes that forbid binding localhost ports, the embedded broker still cannot start — an environment constraint.

If the project already has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you just created the files in the tree and **do not yet have `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`**, you cannot run `./gradlew` yet. Use an installed Gradle to generate the wrapper or run:

~~~bash
gradle test
~~~

**Run a single test:**

~~~bash
./gradlew test --tests demo.messaging.MessagingIntegrationTest.sameMessageTwiceAppliesBusinessEffectOnlyOnce
~~~

**Run the entire class:**

~~~bash
./gradlew test --tests demo.messaging.MessagingIntegrationTest
~~~

**Gradle reports:** `build/reports/tests/test/index.html`; XML `build/test-results/test/TEST-*.xml`. Embedded Kafka logs can be verbose and vary in ordering. The designed expected outcome is **12 JUnit tests PASS**, though this is an **expectation from the code/APIs**, not a claim the suite ran in the learner's environment.

**No fixed stdout snapshot exists**: Kafka offsets, ephemeral ports, consumer thread names, and timing vary per run. Thus the tests assert non-negative/increasing offsets across two sequential sends on the same partition rather than hard-coding offset `0` or port `9092`. `SendResult` does not prove the listener finished, so it is always followed by `await` and SQL assertions.

### 11.1. If broker startup is slow or fails

- Verify JDK 17 is active and Spring Kafka Test matches the Boot BOM.
- Ensure `@EmbeddedKafka` maps `spring.kafka.bootstrap-servers` so the producer does not point to default `localhost:9092`.
- Verify the class uses `kraft=true` supported by Spring Kafka 3.2.
- Inspect `RecordMetadata` logs/broker startup errors, port conflicts, and temporary disk space.
- Raise **bounded test wait timeouts reasonably** for your CI runner; never add arbitrary `Thread.sleep`.
- Never declare the suite green simply because producer `send().get()` returned.

## 12. Testing sending and receiving: common measurement mistakes

### 12.1. “Producer ACK” does not mean the listener ran

~~~java
SendResult<String, OrderCreatedEvent> result =
        publisher.publish(event).get(20, TimeUnit.SECONDS);

assertEquals(
        OrderTopics.CREATED,
        result.getRecordMetadata().topic());
~~~

This snippet uses `publisher`/`event` from the test class. When the future completes, the broker has accepted the record under producer acknowledgment semantics, yet the consumer might not even have partitions assigned yet. Always await **business state** with Awaitility instead of asserting `SELECT` immediately on async paths.

### 12.2. “Listener was invoked” does not mean the DB committed

If you `@SpyBean` the listener and `verify(listener).on(...)`, verification may trigger before the JDBC transaction commits or on a different mock/proxy. This lesson puts the audit callback **after `processOnce` returns** and verifies `processed_message`/`order_points` after awaiting. Even then, proving the consumer offset itself was committed requires separate consumer-group/admin offset inspection; this lesson **does not** claim to verify that milestone.

### 12.3. `@Transactional` on a JUnit test does not roll back the Kafka consumer thread

`@KafkaListener` executes on a listener container thread, not the test caller thread. A test-managed transaction keeps Spring `ThreadLocal` state on the test thread. Placing:

~~~java
@SpringBootTest
@Transactional
class MessageIntegrationTest {
    @Test
    void test() {
        // Send Kafka record; listener writes DB on another thread.
    }
}
~~~

**Illustrative snippet**, not part of the runnable project. The test transaction rolls back DML executed on the test thread itself, yet **cannot roll back inserts/updates committed by the listener thread**. Therefore the project omits `@Transactional` on the JUnit test class, uses unique order IDs, and keeps `@Transactional` on the **business inbox service**.

### 12.4. Kafka idempotent producer does not prevent sending twice from the app

Enabling `enable.idempotence=true` prevents duplicates caused by producer protocol retries, **not** two separate `send(e)` calls made by the application. `sameMessageIdAtTwoOffsetsIsStillOneBusinessEvent` proves two records sit at two distinct offsets while the business effect still occurs only once. The inbox table deduplicates by application message ID.

## 13. Failure and retry cases that must be classified accurately

| Scenario | What consumer should do | Why |
|---|---|---|
| Same `messageId`, same `orderId`/points, already committed | No-op, return normally so offset can be ACKed/committed | Valid duplicate |
| New `messageId`, business order exists | Transactional INSERT receipt + UPDATE points | Valid new event |
| New `messageId`, `orderId` missing | Rollback; brief retry if ordering race, else DLT/alert | Never record a fake receipt |
| Same `messageId` with different payload | Throw/log masked collision; DLT/alert | Never silently treat as a retry |
| DB connection timeout | Controlled retry/backoff | Transient failure; never ACK as success |
| DB unique constraint unrelated to inbox | Do not swallow arbitrary `DataIntegrityViolationException` | Could be a bug or bad data |
| JSON deserialization fails before listener | `ErrorHandlingDeserializer`/DLT recovery | `@KafkaListener` may never run |
| Consumer crashes after DB commit before offset commit | Redelivery → inbox detects duplicate, no-op | At-least-once recovery |
| Incompatible Kafka schema | Contract tests, versioning/DLT | Poison data message |
| External email sent then DB transaction rolls back | Downstream idempotency/outbox | No atomic DB-email transaction |

**Never catch `Exception` and return normally to “avoid retries”**: doing so marks a DB failure as processed even though the business effect never committed. Conversely, never retry all exceptions infinitely without backoff; a single poison record will stall the partition and grow consumer lag forever.

### 13.1. Production retry/DLT configuration (guidance)

With Spring Kafka, options include:
- `DefaultErrorHandler` with `FixedBackOff` or exponential backoff.
- `DeadLetterPublishingRecoverer` to forward unprocessable records to a dead-letter topic.
- `ErrorHandlingDeserializer` to catch deserialization errors and route invalid bytes.
- `@RetryableTopic` for non-blocking retries when topology and ordering allow.
- Micrometer metrics tracking failures, retries, duplicate rate, consumer lag, and DLT depth.

**Note:** This is extension guidance; no DLT broker/topic pipeline is configured in the runnable project. Hence `sameIdWithDifferentPayloadIsRecognizedAsCollision` tests collision detection directly on the service rather than sending a live poison record and waiting on an unconfigured DLT. When building a DLT integration test, provision `orders.created.v1.DLT` or configure routing and inspect real consumer offsets/errors instead of writing a test doomed to time out.

### 13.2. An error handler illustration

~~~java
// Guidance snippet for a context with KafkaTemplate/ConsumerFactory configured.
// Not a standalone runnable config; requires DLT topics and policy.
DefaultErrorHandler handler =
        new DefaultErrorHandler(
                (record, exception) -> {
                    // Route to DLT / metrics / alert, per policy.
                },
                new FixedBackOff(1000L, 2L));
~~~

In this illustration, `FixedBackOff(1000, 2)` schedules 1-second intervals for two retry attempts **per `BackOff` handler settings**, without guaranteeing DLT delivery while the `(record, exception)` lambda is just a comment. Real projects should use `DeadLetterPublishingRecoverer` wired to a `KafkaTemplate` and real broker topics rather than equating lambda logging with DLT integration.

**Do not paste this snippet into the main Gradle project** without adding imports for `org.springframework.kafka.listener.DefaultErrorHandler`, `org.springframework.util.backoff.FixedBackOff`, and a proper handler bean. It is purely illustrative for extension planning.

## 14. Duplicate handling edge cases tests often miss

### 14.1. Duplicates across two consumer instances

An in-JVM `ConcurrentHashMap.newKeySet()` remembers message IDs only in that process; restarts or horizontal scaling lose it. A DB unique constraint makes **multiple consumers sharing a database** race on the same `messageId`: only one transaction inserts the unique key, while the loser rolls back before applying any business effect.

Single-JVM H2 embedded broker tests **do not fully prove** multi-instance PostgreSQL concurrency. Before production:
- Add a PostgreSQL unique index `(consumer_name, message_id)`.
- Run two consumers or integration test instances against the same DB.
- Deliver two concurrent duplicates and assert one business effect.
- Verify the losing transaction rolls back and translates errors cleanly.
- Never remove the unique constraint just because the app has an `if (!processed)` check.

### 14.2. Same `orderId` with a new event ID

In this lesson, **two distinct `messageId`s** for the same `orderId` both add points. That is right when each ID represents an independent business event. If the real domain permits only **one** reward per order, enforce a unique business key like `(order_id, reward_type)` under a different contract; using `orderId` as a Kafka key or arbitrary `messageId` will not solve it.

### 14.3. Same ID with altered payload

When a producer retries, event ID and **payload must not change**. If the same ID arrives with different `points`, the listener must not silently no-op: it could indicate upstream ID reuse for a new event, a serialization bug, or tampering. `matchesStoredReceipt` returns false and the listener throws so DLT/alerts can intervene.

Production systems should log a **safe `messageId` fingerprint** without dumping full JSON containing PII or secrets. You can store schema version, tenant ID, event type, and a payload checksum in the inbox for stronger collision detection.

### 14.4. Inbox TTL and cleanup

Purging receipts after 7 days while Kafka can redeliver events 30 days later causes old messages to re-apply as new. Choose retention based on:
- Kafka topic retention and offset replay/recovery windows.
- Maximum retry/DLT replay intervals.
- Financial/audit obligations.
- Disaster-recovery re-sync windows.
- PII/consent erasure policies.

Never automate `DELETE WHERE processed_at < NOW() - 7D` without an explicit policy. This lesson keeps receipts for the lifetime of the test JVM without introducing arbitrary TTLs.

### 14.5. Kafka exactly-once transactions do not cover JDBC by default

Kafka transactions / Exactly-Once Semantics can coordinate topic outputs and consumer offsets inside Kafka, yet a JDBC DB is a separate resource. Even when a Kafka transaction succeeds, there is no lightweight universal XA transaction making email, PostgreSQL, and Kafka strictly atomic. Use inbox/outbox patterns, idempotency keys, and compensation tailored to business SLAs.

### 14.6. Producer outbox to prevent lost events

Here the test calls `OrderEventPublisher.publish` directly. In a production app, if the business DB commits and `send` fails, the event is lost; if `send` happens before DB commit, consumers can see an event whose order row does not yet exist.

**Transactional outbox pattern:**
1. Within one business DB transaction, INSERT/UPDATE the order and INSERT an outbox record.
2. A worker or CDC reads the outbox and publishes to Kafka.
3. Send retries are safe; keep `messageId` unchanged.
4. Consumers use the inbox unique key to drop duplicates.
5. Monitor outbox backlog, poison events/DLT, cleanup, and schema versions.

An outbox is omitted from the runnable code because it requires a dedicated relay/CDC mechanism; do not mistake the demo publisher for a reliable production outbox.

## 15. Flaky test symptoms and fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| `TimeoutException` on `future.get` | Broker not started, unreachable metadata, network/port | Check `@EmbeddedKafka`, bootstrap servers, and logs |
| Send ACKed yet DB remains 0 | Listener unassigned, deserialization failed, service error | Await with Awaitility; inspect Kafka listener logs |
| `No message received` | Consumer group, topic, JSON deserializer, offset reset | Check topic constant and `@EnableKafka` |
| `ClassNotFoundException` on deserialize | JSON type header from producer in another package | Configure trusted packages/default type/type mapping |
| `SerializationException`/JSON errors | Payload/record contract mismatch | `ErrorHandlingDeserializer` + schema contract |
| H2 table not found | `schema.sql` wrong classpath or SQL init disabled | Place at `src/test/resources/schema.sql`, `spring.sql.init.mode=always` |
| Receipt exists yet points unchanged | Receipt and update in different txs / swallowed error | Ensure `@Transactional` service, insert-first + rollback |
| Duplicate still double-credits points | Keyed by offset/orderId, missing UNIQUE index | Key by business `messageId` + DB unique key |
| Random failures from `Thread.sleep` | Listener runs asynchronously | Await condition with finite timeout |
| `DuplicateKeyException` thrown on duplicate event | Listener failed to catch post-rollback or lacked payload check | Catch exact exception, no-op if payload matches |
| DB deadlock/transaction aborted | Concurrency or catching inside aborted transaction | Roll back first, handle duplicate at boundary |
| `@Transactional` test skips listener DB rollback | Listener runs on a different thread | Unique fixture IDs / out-of-transaction cleanup |
| Tests interfere with each other | Truncating shared tables while listener is still active | Never truncate before tests; use unique UUID IDs |
| Consumer group reads stale events | Reused broker/topic with shared offsets/state | Dedicated group/topic and clean bootstrap lifecycle |
| `@DirtiesContext` slows suite | Restarting broker/context on every method | Use `AFTER_CLASS` if needed, never `AFTER_METHOD` everywhere |
| Parallel Gradle JVMs hit one DB | In-JVM locks/caches don't cross JVMs | Separate test schemas/containers |
| Producer idempotence on yet two records appear | Two app `send` calls get two sequences | Consumer inbox deduplicates by `messageId` |
| Expected record missing from DLT | Recoverer/topic not configured | Configure real DLT, test errors with bounded retries |
| Infinite retry loop | Poison event with unrecoverable error | Classify fatal/non-retryable errors and route to DLT |
| Different `offset`s yet single effect | Expected behavior of semantic deduplication | Never assert Kafka deduplicates by `messageId` |
| Audit metrics grow unbounded | Demo `ConcurrentHashMap` has no TTL | Switch to bounded metrics/observation |
| Double-applied after process restart | Inbox only in-memory or purged too soon | Durable SQL inbox + proper retention |
| Same ID with different payload ignored | Missing receipt payload comparison | Hash/contract comparison and alert |
| Test only mocks `KafkaTemplate` | Skips real serializer/broker/listener | Use `@EmbeddedKafka` or Testcontainers |
| Embedded broker fails in sandbox | Restricted local ports/filesystem | Use permitted container/CI infrastructure |

### 15.1. Debugging a real failure

1. Check producer send future: succeeded or `ExecutionException`?
2. Verify topic, partition, and offset match expectations.
3. Verify `spring.kafka.bootstrap-servers` points to the embedded broker, not default `localhost:9092`.
4. Verify `@KafkaListener` registered, partitions were assigned, and the consumer group is right.
5. If the listener did not run, inspect JSON deserializer settings (trusted packages/default type).
6. If the listener ran yet the DB stayed unchanged, inspect the transaction exception chain and constraints.
7. For duplicates, confirm `messageId` stayed identical across both sends.
8. Verify receipt uniqueness in the DB rather than relying on an in-memory `Set`.
9. Verify new events for the same order get distinct IDs to prevent false deduplication.
10. Verify tests await **after** the send ACK rather than sleeping.
11. For parallel CI, isolate broker topics, group IDs, and DB schemas per worker.
12. Never treat `SendResult` as proof of committed consumer offsets.
13. On missing orders, follow retry/dead-letter policy; never ACK and drop the event.
14. On payload conflicts, investigate upstream ID generation and contracts; never silently ignore.

## 16. Extending: testing retries, DLT, rebalances, and real brokers

### 16.1. `@EmbeddedKafka` vs Testcontainers

| Requirement | `@EmbeddedKafka` | Kafka Testcontainers |
|---|---|---|
| Works without Docker | **Yes** | Usually **no** |
| Tests async `KafkaTemplate`/`@KafkaListener` | **Yes** | **Yes** |
| Fidelity to production brokers | Limited | Higher when matching broker/version/config |
| SASL/TLS/custom networking | Restricted | Easier to model via container config |
| Restart/network fault testing | Complex fixture setup | Can stop/start containers and add Toxiproxy |
| Real PostgreSQL DB testing | Unrelated | Pair with a PostgreSQL container |
| Local port/resource needs in CI | Yes | Yes + Docker daemon |
| Startup time/resources | Usually lean for demos | Depends on container pull/start |

**Migrating to Testcontainers** is not a one-line import change: it requires `spring-boot-testcontainers`, `org.testcontainers:kafka`, JUnit container lifecycle, `@ServiceConnection` or `@DynamicPropertySource`, Docker readiness, and topic provisioning. Never run `@EmbeddedKafka` and a Kafka container simultaneously targeting the same `spring.kafka.bootstrap-servers` without deciding which one is active.

### 16.2. Redelivery after a real crash

An advanced integration test requires:
1. Actively managed broker/test DB lifecycles.
2. Sending event A and letting the listener commit the DB effect.
3. Intentionally killing the consumer **before offset commit**, or performing a controlled offset reset/replay.
4. Restarting the consumer in the same group/partition and observing record A redelivered.
5. Asserting inbox count 1 and order points incremented once.
6. Distinguishing an explicit offset-seek replay test from a true crash window.
7. Checking consumer logs, offset commits, and real DB commits rather than audit counts alone.

The current lesson tests **semantic duplicates from repeated sends**, without claiming to simulate crashes or rebalances. That scope limit is stated explicitly to prevent false conclusions about reliability.

### 16.3. Schema compatibility

Here both producer and consumer share the `OrderCreatedEvent` record. Across multiple teams:
- Write contract tests using JSON Schema, Avro Schema Registry, or Protobuf descriptors.
- Include explicit `eventType`, `schemaVersion`, `messageId`, and `occurredAt`.
- Test adding optional fields and verify older consumers still parse them.
- Test changing types or renaming/removing required fields to catch breaking changes.
- Avoid making Java-specific class names a long-term cross-team wire protocol.
- Scope idempotency keys by event type/version/consumer, not just a raw JSON hash.
- Test deserialization errors with raw bytes and DLT policies **in a separate suite with an error handler configured**.

### 16.4. Testing invalid payloads and poison flows

On malformed JSON, Kafka's `JsonDeserializer` can throw **before entering the listener**. To assert DLT routing, configure `ErrorHandlingDeserializer` as delegate plus `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` for your API version. Send raw bytes via `ProducerRecord<byte[], byte[]>` and await the DLT message. **Never** expect `@KafkaListener(OrderCreatedEvent e)` to receive an unparseable byte stream and return normally.

Production scenarios to cover:
- Missing `messageId` or blank `orderId`.
- Unknown `schemaVersion`.
- Negative `points`, integer overflow, or illegal business values.
- Same ID with different payload.
- DB down/transient network failures with bounded retries.
- DLT publish failure.
- Retry backlogs and consumer lag.
- Out-of-order events and rebalances during DB commit.
- Mixed batches containing both valid and poison records.

## 17. Practice exercises

**Exercise 1 — Broker ACK vs consumer:** Remove `awaitObserved` from the first test and assert the DB immediately after `send().get()`. Why can the test flake even though the producer succeeded?

**Exercise 2 — Kafka offsets:** Send the same `messageId` twice and inspect two differing `RecordMetadata.offset()` values. Why must consumers deduplicate by semantic ID?

**Exercise 3 — Triple duplicate:** Send the same event three times and observe `audit.duplicateCount` and the DB. State the exact invariant.

**Exercise 4 — Two valid events for one order:** Send two distinct `eventId`s for the same order; what should total points be? Why would using `orderId` as the inbox PK break this business rule?

**Exercise 5 — Race condition:** Replace insert-first with `SELECT exists → UPDATE → INSERT`, run two consumer instances concurrently, and observe double effects. Why are a DB unique constraint + transaction a more durable guardrail?

**Exercise 6 — DB rollback:** Send an event for a non-existent order **directly to the service** and verify no receipt remains after the exception. Why would recording the receipt before UPDATE in a separate transaction be dangerous?

**Exercise 7 — Payload conflict:** Keep `messageId` the same while changing `points` from 6 to 999. Why must we not silently no-op? Design a DLT/alert policy.

**Exercise 8 — Producer idempotence:** Keep `enable.idempotence=true` and send the same event twice from the app. Why does the broker still assign two offsets?

**Exercise 9 — `@Transactional` test:** Annotate a JUnit method `@Transactional` and let the listener write to the DB. Why does rolling back the test thread not erase the listener's business effect?

**Exercise 10 — H2 vs PostgreSQL:** Re-run duplicate insert tests on PostgreSQL Testcontainers. Compare error translation, unique constraints, and rollback semantics.

**Exercise 11 — `ErrorHandlingDeserializer`:** Send raw malformed JSON bytes and route them to a real DLT recoverer; verify zero inbox rows.

**Exercise 12 — Retry/backoff:** Make the DB temporarily unavailable once, then recover. Prove bounded retries and a single business effect.

**Exercise 13 — Consumer crash window:** Run a deliberate replay after DB commit but before offset commit; measure consumer offsets and database state.

**Exercise 14 — Outbox:** Inside one DB transaction save Order and outbox; let a worker publish to Kafka. Re-send the outbox record and verify inbox deduplication.

**Exercise 15 — Ordering:** Send two events with the same `orderId` and Kafka key but different event IDs. Check ordering on one partition; test multiple partitions and explain ordering limits.

**Exercise 16 — Schema evolution:** Add an optional `source` field to event JSON and verify older consumers still parse it. Then change `points` from int to string and evaluate the breaking change.

**Exercise 17 — Concurrent instances:** Run two consumers sharing the same DB/schema under different consumer groups (so both receive the same record). Prove the unique inbox enforces one effect even though both receive the message.

**Exercise 18 — Retention:** Delete inbox receipts after a short interval and replay events. Analyze the resulting double effect and propose retention matching business rules.

**Exercise 19 — Observability:** Add counters for received, applied, duplicate, failed, DLT, and consumer lag without keeping message IDs in memory forever.

**Exercise 20 — CI isolation:** Run multiple Gradle forks with embedded brokers or Testcontainers. Design isolated topic/group/DB schema namespaces without using `@DirtiesContext` across the entire suite.

## 18. Pre-CI review checklist

- [ ] Producer sends verify futures/metadata; business effects are never inferred from ACKs.
- [ ] Consumer is a real active `@KafkaListener`, not just a Mockito mock.
- [ ] `@EmbeddedKafka` maps Spring Boot's bootstrap servers property correctly.
- [ ] Topics are provisioned and consumer groups are explicitly configured.
- [ ] JSON serializer/deserializer contracts specify exact types and trusted packages.
- [ ] Business `messageId` is semantic and stable across retries.
- [ ] Kafka keys are chosen for business ordering needs, not confused with idempotency keys.
- [ ] Inbox table has a DB `PRIMARY KEY`/unique key.
- [ ] Receipt insert and business mutation run inside **the same transaction**.
- [ ] Duplicates are caught **after rollback**, scoped strictly to the duplicate-key case.
- [ ] Same ID with different payload is detected and treated as an error.
- [ ] DB unavailable/missing order errors are never swallowed and ACKed as success.
- [ ] Listener success audit runs after DB commit, and tests await async completion.
- [ ] Tests use unique order/message IDs and never truncate shared tables while listeners run.
- [ ] `@Transactional` on the test thread is never assumed to roll back the listener thread.
- [ ] Retry/backoff/DLT/poison payloads have dedicated tests before production deployment.
- [ ] Producer idempotence is never confused with consumer business idempotence.
- [ ] End-to-end exactly-once is never claimed beyond the DB inbox's scope.
- [ ] When production uses PostgreSQL/real Kafka, matching integration suites exist.
- [ ] Tests are never claimed to have passed when only source and expected behavior are shown.

## 19. Official references

- [Spring Boot 3.3 — Apache Kafka Support](https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html): `KafkaTemplate`, `KafkaListener`, properties, and embedded broker testing.
- [Spring Kafka 3.2 — Testing Applications](https://docs.spring.io/spring-kafka/reference/3.2/testing.html): `@EmbeddedKafka`, `bootstrapServersProperty`, JUnit integration, and broker lifecycle.
- [Spring Kafka 3.2 — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/3.2/kafka/receiving-messages/message-listener-container.html): `AckMode.RECORD`/`BATCH`/`MANUAL` and offset commits.
- [Spring Kafka 3.2 — Serialization/Deserialization](https://docs.spring.io/spring-kafka/reference/3.2/kafka/serdes.html): `JsonSerializer`, `JsonDeserializer`, trusted packages, and type metadata.
- [Spring Kafka 3.2 — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/3.2/kafka/annotation-error-handling.html): `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, retries, and DLT.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transaction scope and limits.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `schema.sql`, H2, `spring.sql.init.mode`.
- [Spring Framework — Transaction Declarative Annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `@Transactional` and transaction proxy boundaries.
- [Spring Framework — Test-Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): `ThreadLocal` test transactions.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): `SpringBootTest`, JUnit Jupiter, and `starter-test`.
- [Awaitility — Documentation](https://github.com/awaitility/awaitility/wiki/Usage): bounded asynchronous assertions.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-least-once, producer retries, offsets, and transactions.
- [Testcontainers — Apache Kafka module](https://java.testcontainers.org/modules/kafka/): real broker integration suites.
- [Testcontainers — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): real SQL isolation/transaction validation.

**Conclusion:** A solid messaging test verifies **broker ACK**, **listener delivery**, **DB transaction commit**, and **business invariants** without collapsing those four milestones into one assertion. When at-least-once delivery produces duplicates, rely on a **stable business `messageId`**, a unique inbox constraint, and one transaction combining receipt INSERT + state UPDATE; sending the same ID two or three times still produces **one business effect**. You must also detect same-ID payload collisions, never swallow non-duplicate errors, and plan retries/DLT/outbox for production. `@EmbeddedKafka` and Awaitility make testing the real journey reproducible; H2 and embedded brokers are a starting point, not a substitute for validating real production infrastructure.
