# Verifying Asynchronous Processing with Time-Bounded Conditions

## 1. Lesson goal

In a Spring Boot system using **Messaging** — RabbitMQ, Kafka, JMS, or an event bus — publishing a message successfully and processing a message successfully are **two distinct events**. A producer can finish publishing before the consumer starts processing; the consumer can retry, route to a dead-letter queue (DLQ), write data in a different transaction, or process across multiple worker threads.

Therefore, a test written as:

~~~java
publisher.publish(orderId);
assertEquals("COMPLETED", orderRepository.findStatus(orderId));
~~~

can **fail randomly**: the assertion executes immediately while the message has not yet been consumed by the listener. Conversely:

~~~java
publisher.publish(orderId);
Thread.sleep(3000);
assertEquals("COMPLETED", orderRepository.findStatus(orderId));
~~~

merely replaces a race condition with **blind waiting**. Sometimes the worker finishes in 50 ms yet the test still waits 3 seconds; other times slow CI takes 4 seconds and the test fails, even though the business flow actually works.

The standard solution is to **wait until an observable business condition becomes true, bounded by an explicit deadline**. For Java/JUnit, **Awaitility** is a popular library; it pairs well with Spring Boot, `@RabbitListener`, `KafkaListener`, repositories, caches, or other asynchronous flows.

This lesson belongs to the **Messaging** section of the **Spring Boot – testing** module, covering **Verifying asynchronous processing with time-bounded conditions**. The content progresses from defining reliable conditions to a RabbitMQ/Testcontainers example running real messages, plus pitfalls involving acks, retries, isolation, and parallel CI.

After this lesson, you will be able to:

1. Distinguish **publish**, **broker accept**, **consumer receive**, **business side effect**, **transaction commit**, and **ack/offset commit**.
2. Write `await().atMost(...).untilAsserted(...)` to verify final state without fixed sleeps.
3. Choose `pollInterval`, `pollDelay`, `atMost`, `during`, `atLeast`, and `failFast` for their proper purposes.
4. Scope conditions by **message ID/correlation ID** instead of counting total records or queue size.
5. Verify both the **final outcome** and **business effect count** to detect duplicate delivery.
6. Understand why a consumer reading a message **does not by itself prove** the database transaction committed.
7. Treat `ConditionTimeoutException` as a diagnostic test failure signal rather than a reason to extend sleeps infinitely.
8. Test real RabbitMQ using `RabbitMQContainer`, `RabbitTemplate`, and `@RabbitListener` on Spring Boot 3.3.5.
9. Write positive, business rejection, duplicate message, negative observation, fail-fast, and expected timeout cases.
10. Avoid test flakes under slow broker startup, context caching, delayed delivery, retry/DLQ, multiple consumers, and parallel tests.
11. Evaluate alternatives: `CountDownLatch`, `CompletableFuture`, Mockito `timeout()`, `StepVerifier`, `KafkaTestUtils`, and repository polling.
12. Design deadline-bounded tests aligned with your system's SLA and consistency model.

**Rule:** Wait for a **business-meaningful condition** within a **finite time window**, then fail with the observed state. Never wait by "long enough it's probably done", and never treat `RabbitTemplate.convertAndSend(...)` returning as proof the consumer processed the message.

## 2. Why does Messaging make synchronous assertions error-prone?

Consider an order service publishing an `OrderPaid` message:

~~~text
JUnit test thread
   |
   | publish(orderId = "o-123")
   v
RabbitTemplate / KafkaTemplate
   |
   | Broker accepts / routes message
   v
RabbitMQ queue / Kafka topic
   |
   | Delay due to scheduling / broker / prefetch
   v
Listener thread
   |
   | Validate, transform, call service
   v
Repository / database transaction
   |
   | COMMIT then update read model/cache
   v
Read API / query observed by the test
~~~

At the moment the producer returns, the worker may be at any stage. Consequently:

- The producer cannot know when the consumer will create its side effect.
- Even when broker durability/ack is enabled, the broker accepting a message does not mean the database has committed.
- The consumer can fail, retry, and redeliver; **at-least-once delivery** means the same event may be processed more than once.
- If a test reads from a replica/cache, state may lag behind the transaction commit.
- If a test reuses the same JPA persistence context, it may observe uncommitted data or a stale cache.
- If a test uses `@Transactional`, the test thread's transaction does not span other listener threads.

A sound Messaging test must pick the right **completion milestone**. For instance, if the contract is "the order is marked PAID in the DB", the condition to wait for is **querying the DB and seeing PAID committed**, not "the listener method was called" or "the queue has 0 messages".

### Non-equivalent milestones

| Signal | What it proves | What it does **not** prove |
| --- | --- | --- |
| Producer method returns | Publish call completed per API | Broker routed it or consumer processed it |
| Publisher confirm (RabbitMQ) | Broker confirmed publish per confirms config | Listener finished side effects |
| Message appears in queue/topic | Broker stored/routed the message | Consumer consumed and committed |
| Listener invocation counter | Listener was called at least once | Business transaction committed |
| Consumer ack / Kafka offset commit | Per broker/consumer protocol, progress was marked | External side effects succeeded unless atomicity is guaranteed |
| DB row shows final status | Business state visible in DB at query time | Strictly once or all downstream steps finished |
| HTTP read model updated | External observable state is ready | All other subscribers finished |
| DLQ has message | Message entered error-handling path | Recovery/alerting workflow finished |

**Choose assertions based on the contract.** If the guarantee is "only one email is sent", waiting for DB status PAID is insufficient. You must test idempotency/outbox/fake email gateway in an appropriate test setup.

## 3. From sleep to time-bounded condition waiting

Weak pattern:

~~~java
publisher.publish(orderId);
Thread.sleep(2000);
assertEquals("COMPLETED", state.get(orderId));
~~~

Drawbacks:

- **False negative:** worker finishes in 2.1 s → test fails.
- **Wasted time:** worker finishes in 30 ms → test wastes 1,970 ms waiting.
- **No diagnostics:** unclear whether state is PENDING, RETRYING, or FAILED.
- **Sleep creep:** CI suites slow down by minutes.
- **Blind to failure paths:** the worker might dead-letter immediately, yet the test waits the full duration.
- **No correlation:** state from another test's message might satisfy a broad assertion.

Better pattern:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() ->
        assertEquals("COMPLETED", state.get(orderId)));
~~~

This is an **illustrative snippet**, assuming `state` is a thread-safe observation source and `await()` is statically imported from Awaitility. Meaning:

1. Start observing the condition on a polling schedule.
2. If the assertion fails, retry.
3. **Stop early** as soon as the assertion succeeds.
4. If 10 seconds elapse, throw `ConditionTimeoutException`, failing the test.
5. The specific message is identified by `orderId`.

`atMost(10s)` is a **ceiling**, not "the test always waits 10 seconds". If the system finishes in 200 ms, the test completes right around the next poll after that point.

### Use `until` or `untilAsserted`?

`until` fits a simple predicate:

~~~java
await().atMost(Duration.ofSeconds(5))
    .until(() -> repository.status(orderId) == Status.COMPLETED);
~~~

`untilAsserted` fits when **multiple assertions** and clear failure details are needed:

~~~java
await().atMost(Duration.ofSeconds(5))
    .untilAsserted(() -> {
        assertEquals(Status.COMPLETED,
                repository.status(orderId));
        assertEquals(1L,
                repository.countEffectsFor(orderId));
    });
~~~

`untilAsserted` retries while assertions inside the callback fail. On timeout, Awaitility preserves the last assertion failure to aid debugging. Never place **side-effecting** operations inside the polling callback; they can execute many times.

## 4. Awaitility and time units

Library:

~~~groovy
testImplementation 'org.awaitility:awaitility'
~~~

In a Spring Boot 3.3.5 project, the Awaitility version is managed by Spring Boot dependency management. Even if the test starter brings Awaitility in transitively, declaring it explicitly is beneficial because test sources directly use its API.

Common imports:

~~~java
import java.time.Duration;
import static org.awaitility.Awaitility.await;
~~~

### `atMost`

~~~java
await()
    .atMost(Duration.ofSeconds(8))
    .until(() -> data.getState(id) == COMPLETED);
~~~

Meaning: wait **at most** 8 seconds. If still false, fail. Set a deadline large enough to tolerate normal startup/scheduling without masking a hung consumer.

### `pollInterval`

~~~java
await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(100))
    .until(() -> state.get(id) == COMPLETED);
~~~

Meaning: how frequently the condition is evaluated. 100 ms fits in-memory state or a local test DB; for an expensive remote database, raise it to 250–500 ms or use backoff. **Do not poll thousands of times per second.**

### `pollDelay`

~~~java
await()
    .pollDelay(Duration.ofMillis(50))
    .pollInterval(Duration.ofMillis(100))
    .atMost(Duration.ofSeconds(8))
    .until(() -> state.get(id) == COMPLETED);
~~~

`pollDelay` delays the initial check; usually there is no need to increase it if you want early completion. Defaults depend on version and chosen poll interval; for clarity, specify it intentionally when timing is part of the logic.

### `alias`

~~~java
await()
    .alias("order " + orderId + " eventually completes")
    .atMost(Duration.ofSeconds(8))
    .untilAsserted(() ->
        assertEquals(COMPLETED, state.get(orderId)));
~~~

`alias` attaches the order/test context to timeout messages, especially helpful when a class has multiple awaits or CI logs run in parallel.

### `during`

~~~java
await()
    .during(Duration.ofMillis(300))
    .atMost(Duration.ofSeconds(2))
    .until(() -> state.get(unrelatedId) == UNKNOWN);
~~~

Meaning: the condition must **remain true** continuously for an observation window. A single `assertNull` right after publishing does not prove a state won't appear moments later. Still, **staying true for 300 ms does not prove it will stay true forever**.

### `atLeast`

~~~java
await()
    .atLeast(Duration.ofMillis(200))
    .atMost(Duration.ofSeconds(2))
    .until(() -> observed.get());
~~~

`atLeast` is not a synonym for `during`. It requires the condition **not to complete too early**: if `observed` becomes true before the minimum threshold, Awaitility treats it as a failure. Use it when the contract truly has a **minimum delay** (e.g., an anti-spam cooldown), not to fake "the test should wait at least a little while".

### `failFast`

~~~java
await()
    .failFast("Order has terminal FAILED state",
        () -> status(id) == FAILED)
    .atMost(Duration.ofSeconds(10))
    .until(() -> status(id) == COMPLETED);
~~~

If `FAILED` is known to be a **terminal state**, waiting out the remaining 10 seconds is wasted time. `failFast` stops the test immediately upon observing an unrecoverable state. Only use it for **genuinely terminal** states; if `FAILED` is merely a temporary retry state, `failFast` causes false negatives.

### `ignoreExceptions`

Useful when a specific error represents a valid transient state:

~~~java
await()
    .ignoreExceptionsMatching(error ->
        error instanceof TransientReadException)
    .atMost(Duration.ofSeconds(8))
    .until(() -> readModel.getStatus(id) == COMPLETED);
~~~

**Illustrative snippet:** `TransientReadException` must be defined by the system; this snippet does not compile standalone. Never call `ignoreExceptions()` for all exceptions, hiding authentication failures, schema mismatches, connection leaks, or code bugs. Unrecoverable errors should fail early instead of being swallowed and turning into meaningless timeouts.

## 5. Designing valuable test conditions

A good condition has these properties:

- **Scoped to one message/correlation ID**: does not read a shared global variable.
- **Observable**: tests can query it without forcing the listener to run synchronously.
- **Thread-safe or committed**: avoids data races between listener and JUnit.
- **Stable at its final state**: never sees a temporary `COMPLETED` that later disappears on transaction rollback.
- **Side-effect free**: polling sends no messages, deletes no DB rows, triggers no retries.
- **Bounded by a deadline**: stops and reports failure.
- **Distinguishes terminal failures**: does not wait needlessly once `DEAD_LETTERED`/`FAILED` is known.
- **Diagnostic**: exposes final state, attempt counts, queue/topic, message ID.
- **Test-isolated**: each method uses distinct IDs and has no test order dependency.

### Weak condition: empty queue

~~~java
await().until(() -> queueDepth() == 0);
~~~

Queue depth 0 **does not prove the consumer committed**. The message might be prefetched and **unacked**, retrying, dead-lettered, or grabbed by another consumer. Queue metrics can also lag. To prove business completion, wait on **business state**.

### Weak condition: listener was invoked

~~~java
verify(listener, timeout(5000)).onMessage(any());
~~~

Mockito `timeout` can help in a collaboration test with spies, yet:

- Does not prove the listener was called via a **real broker** if mocked or invoked directly.
- Does not guarantee the listener transaction committed.
- `any()` can match an event from another test.
- Does not check final side effects when the listener invokes another async service.

Even when using spies/mocks to verify invocation, include an integration test observing state by message ID.

### Strong condition: persisted effect

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {
        assertEquals(Status.COMPLETED,
                orderRepository.findStatus(orderId));
        assertEquals(1L,
                outboxRepository.countByOrderId(orderId));
    });
~~~

This is an **architectural snippet**; the repository/entity are not in the runnable project. With a real database, each poll should run in a transaction/connection that can see **committed state**. Avoid reusing a JPA `EntityManager`/session that cached stale state earlier.

## 6. Runnable example: Spring Boot, RabbitMQ Testcontainers, and Awaitility

To test realistically, the example uses **RabbitMQ running in Testcontainers**, without mocking `RabbitTemplate` or calling the listener directly. The test sends a string event to RabbitMQ, the listener runs on Spring AMQP's own thread, and updates a thread-safe `ProcessingLedger` for the test to observe with Awaitility.

**Why use an in-memory ledger instead of a database in the basic example?**

- The lesson's goal is **proper asynchronous waiting**, not implementing JDBC transactions/outboxes.
- Thread-safe `ConcurrentHashMap`/`AtomicInteger` makes cross-thread behavior observable without adding a database.
- We can count **delivery attempts** and **logical effects** to demonstrate idempotency.
- The lesson explicitly states the limitation: updating an in-memory ledger **does not prove a database commit or broker ACK**. Production integration tests should replace the ledger with a real repository/DB/read model when that is the business contract.

The project uses **Java 17, Spring Boot 3.3.5, Gradle Groovy DSL, `spring-boot-starter-amqp`, Awaitility, Testcontainers RabbitMQ, and JUnit 5**. Docker or a compatible container runtime is required to run the integration tests.

### Project structure

~~~text
messaging-await-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/messaging/
    │   ├── MessagingApplication.java
    │   ├── MessagingConfig.java
    │   ├── ProcessingLedger.java
    │   ├── OrderEventListener.java
    │   └── OrderPublisher.java
    └── test/java/com/example/messaging/
        └── RabbitAsyncAwaitTest.java
~~~

Gradle Wrapper scripts/JAR should be generated with a compatible Gradle installation or taken from a repo rather than writing binary JAR contents in Markdown. The source files below are complete for running `gradlew test` once the project has a Wrapper/JDK and Docker.

### `settings.gradle`

~~~groovy
rootProject.name = 'messaging-await-lab'
~~~

### `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.awaitility:awaitility'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Explanation:

- `spring-boot-starter-amqp` provides `RabbitTemplate`, `@RabbitListener`, listener containers, and Spring AMQP auto-configuration.
- `spring-boot-starter-test` contains Spring TestContext/JUnit Jupiter and assertions.
- `org.awaitility:awaitility` provides `await()`, `untilAsserted`, `during`, `failFast`, and deadlines.
- `org.testcontainers:junit-jupiter` provides `@Testcontainers` and `@Container`.
- `org.testcontainers:rabbitmq` provides `RabbitMQContainer` for a real AMQP broker.
- `useJUnitPlatform()` ensures Gradle runs JUnit Jupiter properly.
- Testcontainers/Awaitility versions are managed by the Spring Boot BOM. `org.testcontainers:rabbitmq` is the Testcontainers **1.x** coordinate matching Boot 3.3; Testcontainers 2.x uses different module/group names, so do not copy 2.x dependencies into a 3.3 build without aligning compatibility.
- No PostgreSQL/H2, Kafka, web server, or `@Async` is needed to demonstrate Awaitility logic.
- No production broker credentials. Testcontainers provides isolated RabbitMQ test user/password inside the ephemeral container.

### `MessagingApplication.java`

~~~java
package com.example.messaging;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

`@EnableRabbit` enables annotated listener endpoints explicitly. Spring Boot normally auto-configures Rabbit listener container factories when AMQP infrastructure is present. The root application sits in `com.example.messaging` so Spring Boot scans all remaining classes.

The demo project **does not** set a default RabbitMQ URL pointing at production in main resources. Tests supply the RabbitMQ endpoint via `@DynamicPropertySource` before Spring builds the connection factory.

### `MessagingConfig.java`: test queue declared by Spring AMQP

~~~java
package com.example.messaging;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MessagingConfig {

    @Bean
    Queue ordersQueue(
            @Value("${demo.orders.queue}") String name) {

        return QueueBuilder.nonDurable(name)
                .autoDelete()
                .build();
    }
}
~~~

`QueueBuilder.nonDurable(name).autoDelete()` creates a queue for test/demo purposes, not a policy for production durable queues. It allows the test to assign a unique queue name without colliding with queues in other suites.

Spring Boot/`RabbitAdmin` can auto-declare the `Queue` bean on RabbitMQ when the connection opens. In the test below, we also call `AmqpAdmin.declareQueue(...)` in `@BeforeEach` to ensure the queue exists before publishing. Re-declaring the **exact same name and attributes** is idempotent per broker protocol; declaring the same name with different durability/arguments can be rejected by RabbitMQ with `PRECONDITION_FAILED`.

### `ProcessingLedger.java`: thread-safe state and effect counting

~~~java
package com.example.messaging;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class ProcessingLedger {

    public enum State {
        UNSEEN, COMPLETED, DECLINED
    }

    private final ConcurrentMap<String, State> states =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> deliveries =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> effects =
            new ConcurrentHashMap<>();

    private final Set<String> handledIds =
            ConcurrentHashMap.newKeySet();

    public void record(String eventId, State outcome) {
        deliveries.computeIfAbsent(
                eventId, id -> new AtomicInteger())
                .incrementAndGet();

        // Prevent repeating the logical effect for the same eventId.
        if (handledIds.add(eventId)) {
            effects.computeIfAbsent(
                    eventId, id -> new AtomicInteger())
                    .incrementAndGet();
            states.put(eventId, outcome);
        }
    }

    public State state(String eventId) {
        return states.getOrDefault(eventId, State.UNSEEN);
    }

    public int deliveryCount(String eventId) {
        AtomicInteger value = deliveries.get(eventId);
        return value == null ? 0 : value.get();
    }

    public int effectCount(String eventId) {
        AtomicInteger value = effects.get(eventId);
        return value == null ? 0 : value.get();
    }
}
~~~

**Why use concurrent collections?** The JUnit thread reads `states` while the RabbitMQ listener thread writes. `HashMap` does not provide the required memory visibility/thread safety. `ConcurrentHashMap` and `AtomicInteger` give the test a sound basis for observing cross-thread updates.

**Why `handledIds.add(eventId)`?** The same ID may be delivered multiple times (intentional duplicate send in a test, or broker redelivery). `Set.add` returns `true` only once; the demo increments `effects` only once. This illustrates **idempotency by event ID**.

**Critical limitation:** this in-memory Set/ledger is **not** production idempotency. If the process crashes after marking handled yet before writing to a DB, or across multiple JVM instances, state is neither atomic nor durable. Production should use database unique constraints/idempotency keys, an inbox table, transactions, or a suitable outbox pattern.

**Definition of "deliveryCount":** the number of times `record` was called in the demo. It is not the broker's total delivery count across all consumers or producer send count; it only observes deliveries that reached this business listener.

### `OrderEventListener.java`: consumer running from the broker

~~~java
package com.example.messaging;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final ProcessingLedger ledger;

    public OrderEventListener(ProcessingLedger ledger) {
        this.ledger = ledger;
    }

    @RabbitListener(queues = "${demo.orders.queue}")
    public void receive(String payload) {
        int separator = payload.indexOf('|');

        if (separator <= 0
                || separator == payload.length() - 1) {
            throw new IllegalArgumentException(
                    "Expected TYPE|eventId");
        }

        String type = payload.substring(0, separator);
        String id = payload.substring(separator + 1);

        switch (type) {
            case "COMPLETE" ->
                    ledger.record(
                        id, ProcessingLedger.State.COMPLETED);

            case "DECLINE" ->
                    ledger.record(
                        id, ProcessingLedger.State.DECLINED);

            default ->
                    throw new IllegalArgumentException(
                        "Unknown event type: " + type);
        }
    }
}
~~~

Message payloads stay **String** to avoid adding JSON converters/schemas to an Awaitility lesson. `RabbitTemplate.convertAndSend` and `@RabbitListener(String)` use the string-compatible message converter. If production uses JSON/Avro/Protobuf, test serialization/deserialization separately and use the matching converters.

**The `DECLINED` state in the demo is a business-level rejection** — the listener **successfully processes the message**, records `State.DECLINED`, and returns normally. It is **not a broker connection error**, not a listener exception, and not automatically routed to a DLQ.

In Spring AMQP, a listener container in `AUTO` mode normally ACKs when the listener returns successfully; when it throws an exception, requeue/retry/DLQ depends on config. Do not infer an ACK merely because the ledger updated — at the moment Awaitility observes the state, the ACK might still be in flight.

### `OrderPublisher.java`: real producer via `RabbitTemplate`

~~~java
package com.example.messaging;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final RabbitTemplate rabbitTemplate;
    private final Queue ordersQueue;

    public OrderPublisher(
            RabbitTemplate rabbitTemplate,
            Queue ordersQueue) {

        this.rabbitTemplate = rabbitTemplate;
        this.ordersQueue = ordersQueue;
    }

    public void publish(String type, String eventId) {
        String payload = type + "|" + eventId;

        // Empty exchange: AMQP default exchange.
        // Routing key matches the queue name exactly.
        rabbitTemplate.convertAndSend(
                "", ordersQueue.getName(), payload);
    }
}
~~~

The producer sends to RabbitMQ's **default exchange** with the queue name as the routing key. Once the queue is declared, RabbitMQ creates the matching default binding. This is a concise publish path for the lesson, **not** a replacement for production exchange/routing/binding management.

**`convertAndSend` returning does not prove the listener finished.** To check broker accept/routing, write a separate publisher confirms/returns test. This lesson focuses on **business state after the listener processes the message**.

## 7. Real integration tests with RabbitMQ and Awaitility

**`src/test/java/com/example/messaging/RabbitAsyncAwaitTest.java`**

~~~java
package com.example.messaging;

import java.time.Duration;
import java.util.UUID;

import org.awaitility.core.ConditionTimeoutException;
import org.awaitility.core.TerminalFailureException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.Queue;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
    classes = MessagingApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.rabbitmq.listener.simple.acknowledge-mode=auto",
        "spring.rabbitmq.listener.simple.default-requeue-rejected=false"
    })
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RabbitAsyncAwaitTest {

    @Container
    static final RabbitMQContainer broker =
            new RabbitMQContainer(
                    "rabbitmq:3.13-management-alpine")
                .withAdminUser("test_user")
                .withAdminPassword("test_password");

    private static final String QUEUE_NAME =
            "await.orders." +
            UUID.randomUUID().toString().replace("-", "");

    @DynamicPropertySource
    static void rabbitConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host",
                broker::getHost);
        registry.add("spring.rabbitmq.port",
                broker::getAmqpPort);
        registry.add("spring.rabbitmq.username",
                broker::getAdminUsername);
        registry.add("spring.rabbitmq.password",
                broker::getAdminPassword);
        registry.add("demo.orders.queue",
                () -> QUEUE_NAME);
    }

    @Autowired
    private OrderPublisher publisher;

    @Autowired
    private ProcessingLedger ledger;

    @Autowired
    private Queue ordersQueue;

    @Autowired
    private AmqpAdmin admin;

    @BeforeEach
    void ensureQueueExistsBeforePublish() {
        admin.declareQueue(ordersQueue);
    }

    private String newEventId() {
        return "evt-" + UUID.randomUUID();
    }

    @Test
    void eventuallyCompletesMessageWithBoundedAwait() {
        String eventId = newEventId();

        assertEquals(
                ProcessingLedger.State.UNSEEN,
                ledger.state(eventId));

        publisher.publish("COMPLETE", eventId);

        await()
            .alias("complete event " + eventId)
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                assertEquals(
                    ProcessingLedger.State.COMPLETED,
                    ledger.state(eventId));
                assertEquals(1,
                    ledger.effectCount(eventId));
            });
    }

    @Test
    void businessDeclineIsACompletedConsumerOutcome() {
        String eventId = newEventId();

        publisher.publish("DECLINE", eventId);

        await()
            .alias("decline event " + eventId)
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                assertEquals(
                    ProcessingLedger.State.DECLINED,
                    ledger.state(eventId));
                assertEquals(1,
                    ledger.effectCount(eventId));
            });
    }

    @Test
    void duplicateMessagesHaveOnlyOneLogicalEffect() {
        String eventId = newEventId();

        publisher.publish("COMPLETE", eventId);
        publisher.publish("COMPLETE", eventId);

        await()
            .alias("both deliveries for " + eventId)
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                assertTrue(
                    ledger.deliveryCount(eventId) >= 2);
                assertEquals(1,
                    ledger.effectCount(eventId));
                assertEquals(
                    ProcessingLedger.State.COMPLETED,
                    ledger.state(eventId));
            });
    }

    @Test
    void anotherEventIdRemainsUnseenDuringObservationWindow() {
        String known = newEventId();
        String unrelated = newEventId();

        publisher.publish("COMPLETE", known);

        await()
            .atMost(Duration.ofSeconds(10))
            .until(() ->
                ledger.state(known)
                    == ProcessingLedger.State.COMPLETED);

        // A single assertion right after publish is insufficient.
        // Proves only that unrelated remains unchanged for 350 ms.
        await()
            .alias("unrelated event stays untouched")
            .during(Duration.ofMillis(350))
            .atMost(Duration.ofSeconds(3))
            .pollInterval(Duration.ofMillis(50))
            .until(() ->
                ledger.state(unrelated)
                    == ProcessingLedger.State.UNSEEN);
    }

    @Test
    void terminalDeclineCanAbortAWaitImmediately() {
        String eventId = newEventId();
        publisher.publish("DECLINE", eventId);

        TerminalFailureException failure = assertThrows(
            TerminalFailureException.class,
            () -> await()
                .alias("event should complete")
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(50))
                .failFast(
                    "DECLINED is terminal",
                    () -> ledger.state(eventId)
                        == ProcessingLedger.State.DECLINED)
                .until(() ->
                    ledger.state(eventId)
                        == ProcessingLedger.State.COMPLETED));

        assertTrue(failure.getMessage()
                .contains("DECLINED is terminal"));
    }

    @Test
    void unpublishedEventTimesOutWithinFiniteDeadline() {
        String eventId = newEventId();

        ConditionTimeoutException failure = assertThrows(
            ConditionTimeoutException.class,
            () -> await()
                .alias("no event was published")
                .atMost(Duration.ofMillis(350))
                .pollInterval(Duration.ofMillis(50))
                .until(() ->
                    ledger.state(eventId)
                        == ProcessingLedger.State.COMPLETED));

        assertNotNull(failure);
        assertEquals(
            ProcessingLedger.State.UNSEEN,
            ledger.state(eventId));
    }
}
~~~

### Test 1: Positive eventual processing

Sequence:

1. Generate a fresh `eventId` and verify initial state `UNSEEN`.
2. Send `COMPLETE|eventId` via a **real `RabbitTemplate`** to RabbitMQ.
3. The listener thread receives the payload and calls `ledger.record`.
4. Awaitility polls the condition for at most 10 seconds.
5. Once `state == COMPLETED` **and** `effectCount == 1`, the test passes immediately.
6. If it does not complete before the deadline, `ConditionTimeoutException` fails the test.

Unlike fixed sleep, the test finishes once **the state meets the contract**. If RabbitMQ or the listener disconnects, the condition does not silently "become true".

### Test 2: Business rejection is not an infrastructure failure

The `DECLINE` event is processed by the listener, recording `State.DECLINED` and `effectCount == 1`. The test verifies that a "declined order" case is a **valid business outcome**, distinct from a consumer throwing an exception/poison message or a broker failure.

If business rules require declined events to enter a DLQ, design different listener/error handling and test the DLQ separately. Never call every `DECLINED` state a "failed message"; in some systems, declining is a normal outcome.

### Test 3: At-least-once delivery and idempotency

We intentionally publish **the same `eventId` twice**. Results:

- `deliveryCount(eventId) >= 2` proves the listener recorded at least two deliveries of that event.
- `effectCount(eventId) == 1` proves the **demo logic** counts only one logical effect for the key.
- `state(eventId) == COMPLETED` proves the final outcome is completed.

We use `>=2` rather than `==2` because broker/consumer redeliveries can occur under failure conditions. This test does not yet prove multi-process/durable-transaction idempotency; for that, use database unique constraints or inbox/outbox integration tests.

**Race note:** A concurrent listener can increment `deliveryCount` before `state` is stored. Therefore, the `untilAsserted` block checks **all three** and retries until they hold simultaneously. Never split it into "await count >= 2" and immediately assert effect if effect is still being updated.

### Test 4: Observing a negative condition over a time window

`unrelated` was never published. A single `assertEquals(UNSEEN, ...)` right at the start is true, yet does not verify an **observation window**. `during(350ms)` checks that the condition holds continuously for 350 ms within a 3-second deadline.

**Logical limitation:** no finite test can prove an event will never be created in the future. It only guards the specified observation window. If the requirement is "do not publish before a 1-minute deadline", you need an observation window matching the contract (accepting the test cost) or a contract/test seam checking the scheduling policy directly.

### Test 5: Fail-fast when state is terminal

The test produces `DECLINE` while waiting for `COMPLETED`. Since `DECLINED` is treated as terminal in the demo, `failFast` throws `TerminalFailureException` **before the 10-second deadline expires**, as soon as `DECLINED` is observed.

The test wraps it in `assertThrows(TerminalFailureException.class,...)` to **demonstrate and verify the fail-fast mechanism**. In normal business success tests, this exception **must not be caught to pass**; it should fail the test and clearly state the reason.

### Test 6: Timeout is a result of the wait utility, not a fake broker error

The test publishes no event. `state == COMPLETED` will certainly not occur for that isolated `eventId`. Awaitility throws `ConditionTimeoutException` after the finite deadline, and `assertThrows` turns this into a unit/integration test of the **waiting mechanism itself**.

When verifying real business flows, **never wrap `await` in `assertThrows`** just to keep the suite green if the consumer stops processing. In production tests, timeouts should **fail the test**, while expected-timeout belongs only to negative scenarios or helper verification.

## 8. Expected results and how to run

The project has **6 `@Test` methods** in `RabbitAsyncAwaitTest`. That is the official test count; `@BeforeEach` and helper `newEventId` are not test methods.

| Test method | Wait condition | Expected outcome |
| --- | --- | --- |
| `eventuallyCompletesMessageWithBoundedAwait` | `COMPLETED` + `effect=1` | PASSES early once processing completes |
| `businessDeclineIsACompletedConsumerOutcome` | `DECLINED` + `effect=1` | PASSES on business decline |
| `duplicateMessagesHaveOnlyOneLogicalEffect` | `deliveries>=2` + `effects=1` | PASSES when demo idempotency works |
| `anotherEventIdRemainsUnseenDuringObservationWindow` | Other ID stays `UNSEEN` for 350 ms | PASSES over observation window |
| `terminalDeclineCanAbortAWaitImmediately` | Fail-fast `DECLINED` while awaiting `COMPLETED` | PASSES because `TerminalFailureException` is expected |
| `unpublishedEventTimesOutWithinFiniteDeadline` | No publish → 350 ms deadline | PASSES because timeout is expected and verified |

Run from the project root with Gradle Wrapper and Docker/compatible container runtime:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run just this class:

~~~bash
./gradlew test --tests 'com.example.messaging.RabbitAsyncAwaitTest'
~~~

Standard Gradle reports:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.messaging.RabbitAsyncAwaitTest.xml
~~~

With compatible JDK 17, Boot 3.3.5, Testcontainers 1.x, Docker, and RabbitMQ image, **6 tests are expected to pass**. This is a **prediction from the code and semantics**, not a claim of running Gradle/Testcontainers on the learner's machine. RabbitMQ startup depends on the host/CI; broker logs, port mappings, and timings are not fixed.

If Gradle reports `UP-TO-DATE` or `FROM-CACHE`, the test task may have been reused. To force re-execution for diagnostics:

~~~bash
./gradlew test --rerun-tasks
~~~

If no Wrapper is present yet but a compatible Gradle is installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Commit Wrapper scripts/JAR per repository policy. Do not upgrade Gradle/Boot/test library versions of a real project merely because the tutorial uses 3.3.5.

### When Docker is unavailable

Testcontainers can fail reporting no Docker environment found or an image pull failure. That is an **infrastructure error**, not proof that business logic is wrong. Avoid "fixing" it by deleting broker integration tests or switching to mocks and claiming end-to-end Messaging is tested. Instead, provision the runner with a container runtime, socket permissions, image registry access, and proper networking.

## 9. Which milestone is enough to say "processing is done"?

Systems often have multiple definitions of **done**:

### A. Listener method ran

For instance, a test increments an `AtomicInteger` at the top of the listener. This proves **handler entry**, not that validation/persistence/commit succeeded. If the listener throws after incrementing the counter, the test can pass falsely.

### B. Listener returned normally

In Spring AMQP `AUTO` mode, a listener returning normally usually leads to a container-managed broker ACK. However, an assertion on in-memory state updated **inside the listener** can pass **before the listener actually returns and sends the ACK**.

### C. Business database commit succeeded

If the listener calls a `@Transactional` service with `REQUIRED`, the transaction normally commits when the service method returns through its proxy; the test should query the row from a **separate read-only transaction/connection** after commit. With JPA, `save`/`flush` inside a transaction does not prove commit.

### D. Outbox written and downstream event sent

When a workflow spans stages, state in one service proves only one stage. You may need to wait for a composite condition of **record committed + outbox published + consumer projection updated**. Assert everything required by the contract.

### E. Message ACKed or offset committed

Broker ACK/offset commit is a distinct signal. If you need to verify exact ACK/offset behavior, write a test using the corresponding broker management/client controls rather than only observing in-JVM state.

### F. External system side effect occurred

For email, payment gateways, HTTP partners, or S3/file/object storage, stub/spy *at the proper boundary* and verify the actual event. A DB status row might be written before the external call succeeds.

**Tip:** Name test methods after the **observable outcome**: `eventuallyUpdatesOrderProjection` is better than `consumerReceivedMessage`. Naming helps reviewers see what evidence the test actually guards.

## 10. Testing with a real database instead of an in-memory ledger

In applications using Spring Data JPA/JDBC, the target condition is typically:

~~~java
publisher.publish(new OrderPaidEvent(orderId));

await()
    .alias("Order " + orderId + " committed as PAID")
    .atMost(Duration.ofSeconds(12))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() -> {
        OrderEntity order =
                orderRepository.findById(orderId).orElseThrow();
        assertEquals(OrderStatus.PAID, order.getStatus());
        assertEquals(1L,
                paymentOutboxRepository.countByOrderId(orderId));
    });
~~~

**This is an architectural snippet, not standalone runnable:** the sample project has only `ProcessingLedger`, not `OrderEntity`/JPA repositories. With real DB tests:

- `findById` must observe fresh commits, not query inside an old transaction snapshot.
- If the test class has `@Transactional`, JUnit holding an open transaction can hide new committed state or cause locks.
- Do not reuse an `EntityManager` that already cached the entity before message processing.
- When needed, clear the persistence context, use an appropriate read-only `REQUIRES_NEW` transaction, or query via a fresh JDBC connection.
- DB/read-model queries must target the right datasource/tenant and stay isolated from other tests.
- When the application has replica lag, deadlines must reflect real consistency promises.

### Common mistake with `@Transactional` on JUnit tests

~~~java
@SpringBootTest
@Transactional
class AsyncMessagingTest {
    // Listener runs on a different thread.
}
~~~

A transaction managed by Spring TestContext on the test thread **does not propagate automatically** to the Rabbit listener thread. If the test opens and holds an uncommitted transaction and publishes an event with the new record's ID, the listener thread may **not see the row** due to isolation; it will retry/fail. Sleeping 10 seconds still cannot fix an uncommitted transaction.

The right design is typically:

1. Create fixtures in a committed transaction before publishing, or use `TransactionTemplate` to commit explicitly.
2. Publish the message once the fixture is visible to the listener thread.
3. Wait for final database state through a separate connection/transaction.
4. Clean up committed data after the test via a real committed transaction.
5. Never assume test-managed rollback deletes data committed by a listener thread.

### When preparing input data before the test

One technique is `@BeforeTransaction` to set up committed data when a test class is transactional; or use `TransactionTemplate` inside a non-`@Transactional` test. Either way, understand transaction boundaries and design cleanup deliberately — simply putting `@BeforeEach` on a transactional test will not make rows visible to a listener thread.

## 11. Good conditions for retries, DLQ, and poison messages

In practice, consumers do not always succeed on the first attempt. Model:

~~~text
NEW -> ENQUEUED -> PROCESSING
                       |
                       +-- COMPLETED
                       |
                       +-- RETRYING -> PROCESSING
                       |
                       +-- DEAD_LETTERED / FAILED_FINAL
~~~

If the contract permits retries, do not `failFast` merely upon seeing `RETRYING` or a transient error. Only fail fast on **truly terminal states**, such as `DEAD_LETTERED` when no automatic recovery runs in the test.

### Waiting for success with fail-fast

~~~java
await()
    .alias("event " + eventId + " reaches terminal outcome")
    .atMost(Duration.ofSeconds(15))
    .failFast(
        "event dead-lettered",
        () -> statusRepository.status(eventId)
                == Status.DEAD_LETTERED)
    .untilAsserted(() ->
        assertEquals(
            Status.COMPLETED,
            statusRepository.status(eventId)));
~~~

**Illustrative snippet**; `statusRepository`/`Status` must be defined in the real system. With fail-fast, the test directly explains why it could not succeed instead of merely reporting "condition timed out".

### Verifying the DLQ

A DLQ test can:

- Send an intentionally invalid message with an isolated `eventId`.
- Configure the consumer to reject/no-requeue or limit retries just like production.
- Wait for the message to appear in the DLQ or in persisted error state with a correlation ID.
- Assert retry count, metadata, original payload, and error reason per contract.
- Clean up test queues/messages without reading or deleting from production brokers.

**Do not use `queue.size()==0` as proof that DLQ handling succeeded**. A poison message might have moved to the DLQ so the main queue is empty while the workflow is still `FAILED`.

### Spring AMQP default ACK and requeue

With Spring AMQP listener containers, `AcknowledgeMode.AUTO` usually ACKs when the listener returns; if the listener throws, the broker requeues or rejects depending on `defaultRequeueRejected`, retry interceptors, and error handlers. Default behavior can retry infinitely in certain configurations unless tuned.

The demo project sets `spring.rabbitmq.listener.simple.default-requeue-rejected=false` to avoid infinite requeue loops on invalid payloads. **It does not create a DLQ by itself**: routing rejected messages to a DLQ requires broker topology with dead-letter exchanges/bindings or matching policies.

If using `AcknowledgeMode.MANUAL`, the listener must ACK/NACK with the exact delivery tag/channel, and tests must cover the ACK paths explicitly. Never copy `AUTO` assertions to a manual-ack app without checking transaction/reliability semantics.

## 12. Remember: "polling callbacks must be pure observers"

Awaitility calls predicates/assertions many times. What **not** to do inside a callback:

~~~java
await().until(() -> {
    publisher.publish("COMPLETE", eventId);
    return repository.status(eventId) == COMPLETED;
});
~~~

Every time the condition is not yet met, the test publishes another message, altering the stimulus; this causes duplicate deliveries and confusing races. Publish **once before `await`**.

Also avoid:

- `repository.deleteAll()` inside the condition.
- Long manual `Thread.sleep` inside the condition.
- Calling `listener.process(event)` directly inside the condition.
- Opening unclosed JDBC connections on every poll.
- Logging full payloads/credentials every 50 ms.
- Calling a state-mutating REST endpoint when you only mean to inspect status.
- Calling `assertThrows` to swallow important exceptions.
- Creating unclosed `EntityManager`s or leaking JDBC resources.

A safe predicate should only read state/metrics/test DB and return fast. If a query has 2-second latency, setting `pollInterval(10ms)` will not make the test finish proportionally faster; it increases load, pool contention, and flakiness.

## 13. Concurrent data and memory visibility

An often-overlooked bug:

~~~java
class UnsafeObserver {
    boolean completed;
}
~~~

The JUnit thread polls `completed` while the worker thread sets `completed = true`. Without `volatile`, locks, atomics, or a concurrent collection, the Java Memory Model **does not guarantee** the polling thread sees the update promptly. The test can fail even after the worker set the value.

Proper choices:

- `AtomicBoolean` or `AtomicReference<State>`.
- `volatile` when only visibility of a single independent value is needed.
- `ConcurrentHashMap`/`ConcurrentMap` and `AtomicInteger`.
- `CountDownLatch` for signaling with API-guaranteed happens-before.
- Database transactions with proper isolation/commit semantics.
- Message queues and thread-safe observability collectors.

`Awaitility` **does not magically make arbitrary Java variables thread-safe**. It provides the polling/waiting API; the app/test must ensure synchronization/visibility of observed state.

### Multiple fields must stay consistent

If a listener writes:

~~~java
status = COMPLETED;
effects.incrementAndGet();
~~~

a polling test may observe `status == COMPLETED` **before** `effects == 1`. Hence `untilAsserted` should check both together; or production models should update both fields in the same database transaction. Do not assume two separate `ConcurrentMap` updates form an atomic snapshot automatically.

### Using `AtomicReference` in unit tests

~~~java
AtomicReference<State> observed =
        new AtomicReference<>(State.PENDING);

someExecutor.submit(() -> observed.set(State.COMPLETED));

await()
    .atMost(Duration.ofSeconds(2))
    .until(() -> observed.get() == State.COMPLETED);
~~~

**Short snippet**, needing `State`/`someExecutor` and executor cleanup. It demonstrates visibility, **not broker testing**. Never call every test with a worker thread a messaging integration test.

## 14. Counting accurately: processed, delivered, acknowledged, and side effects

Some tests use counters:

~~~java
assertEquals(1, processedCount.get());
~~~

This is insufficient when:

- The counter increments at the top of the listener and business logic fails afterwards.
- An event is delivered twice, yet the business side effect still ran only once.
- An event retries and succeeds on attempt 3; delivery count is 3 while business effect is 1.
- The listener completes yet ACK is lost, and the broker redelivers later.
- Tests read a shared counter across methods/classes.

The demo separates:

- `deliveryCount(eventId)`: how many times the listener called `record`.
- `effectCount(eventId)`: how many times demo logic applied the idempotent effect.
- `state(eventId)`: final business outcome.

In real apps, prefer **business artifacts** as the criterion: a unique DB row, outbox event, settlement transaction, or sandbox email request; in-JVM counters are mainly debugging aids.

### Once-only caution

Messaging typically provides **at-least-once delivery**. Observing `effectCount==1` on a duplicate test event must not be extrapolated into end-to-end broker/provider exactly-once guarantees. Verify:

1. Can the producer resend?
2. Can the broker redeliver after a lost ACK?
3. Can multiple consumers receive the same event ID?
4. Where is the consumer deduplication key stored?
5. Are DB writes and ACKs atomic?
6. Does outbox/inbox/transaction design guard against partial failures?

An **idempotent consumer** policy is generally far more realistic than promising "the broker delivers messages only once".

## 15. `CountDownLatch`, `CompletableFuture`, Mockito, and Awaitility

### `CountDownLatch`

~~~java
CountDownLatch latch = new CountDownLatch(1);

// Listener after processing:
latch.countDown();

// Test:
assertTrue(latch.await(5, TimeUnit.SECONDS));
~~~

This snippet assumes test and listener share **the same valid latch instance**. Latches work for waiting on signals, yet have drawbacks:

- If the listener calls `countDown()` **before the DB commit**, the latch passes before data is committed.
- If the signal is missed because the test resets the latch after publishing, the test times out.
- Easy to leak state across methods if a shared static latch is used.
- Does not replace detailed assertions on state/business effects.
- Latches have a fixed count; multi-stage workflows need explicit coordination.

Latches fit when **the signal itself is the contract** and is fired at the exact right moment. For repositories/read models, Awaitility condition polling reads more naturally.

### `CompletableFuture`

~~~java
CompletableFuture<Result> future = service.submitAsync(command);

Result result = future.get(5, TimeUnit.SECONDS);
assertEquals(Result.OK, result);
~~~

Illustrative snippet without a runnable `service`/`Result` in the lab. Futures have explicit timeouts and work well when an API **returns a future representing completion itself**. However, producers sending messages to a broker normally return **without a future** representing consumer completion; a send `CompletableFuture` cannot prove downstream DB state.

### Mockito `timeout()`

~~~java
verify(notificationAdapter, timeout(5000))
    .notify(eq(orderId));
~~~

Usable for verifying an interaction at a unit/integration seam with a spy. However:

- Mock invocation may happen without a committed transaction.
- Spy beans can complicate test setup and alter class proxies.
- Does not prove RabbitMQ/Kafka works unless the test sends real broker events.
- Boot annotation names vary by version (`@MockBean`, `@MockitoBean`); verify against your version rather than mixing Boot 4 docs into Boot 3.3.

### Awaitility

Pick when the target state is **eventually observable**, has a read-only API, and can be polled safely. Suits DB queries, caches, HTTP GET read models, in-memory concurrent state, and scoped message counts.

### Reactor `StepVerifier`

When code returns `Mono`/`Flux`, use `StepVerifier` to verify stream signals. Still, a `Mono<Void>` producer publish completing does not represent consumer commit. To verify **downstream eventual state**, you may still need Awaitility on a repository or appropriate stream/tracing.

## 16. Kafka and JMS: shared principles, distinct semantics

### Kafka

With `@KafkaListener` and `KafkaTemplate`, tests can:

1. Provision a topic/test broker with `@EmbeddedKafka` or Kafka Testcontainers.
2. Publish an event with an `eventId` to the topic.
3. Wait for the business projection/repository to reach the target status.
4. Verify consumer group/offset/retry/DLT separately when part of the contract.

Kafka pitfalls:

- Offset commit and database commit are not automatically atomic.
- Kafka partition ordering holds only within one partition, not across all consumers/globally.
- Tests sharing a consumer group can "steal" events from each other.
- Consumers may receive partition assignments late; timeouts must account for startup/join latency.
- Retry topics and DLTs can advance the main topic consumer before business processing is done.
- `KafkaTestUtils` helps read records with a test consumer, yet a test consumer reading an event **does not mean another listener finished**.

Architectural snippet:

~~~java
kafkaTemplate.send("order-events", orderId, event);

await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertEquals("DONE",
            readModel.findStatus(orderId)));
~~~

This is not standalone; it needs Kafka dependencies, topics, and a defined read model. With Kafka, do not blindly map RabbitMQ `@RabbitListener` ACK semantics onto Kafka offsets.

### JMS

With `@JmsListener` and `JmsTemplate`, the condition-waiting architecture is similar, yet ACK modes, transacted sessions, and redelivery policies belong to the JMS provider. A JMS test sending a message must still await the **business outcome** when processed on a listener thread. "Queue empty" likewise does not guarantee external side effects committed.

### Spring application events

`@Async @EventListener` or `@TransactionalEventListener` can run asynchronously inside the JVM **without a broker**. Awaitility remains useful for eventual state, yet never label that RabbitMQ/Kafka integration coverage when no real broker is involved.

## 17. Waiting deadlines: how long is enough?

Setting `atMost(Duration.ofSeconds(10))` is not a magic number. Deadlines should be calculated from:

- What is the system's message delivery/processing SLA?
- Did container/listener startup happen **before** or **after** the await starts?
- Does CI have slower CPU/IO scheduling than a laptop?
- Are retries/backoff allowed, e.g., 3 attempts × 2 s?
- What is typical DB commit/projection lag?
- How many tests run in parallel competing for resources?
- What is the longest acceptable slow test before failing fast on a real bug?

Example:

~~~text
Event processing budget in test:
  broker dispatch + scheduling  < 1.0 s
  business logic               < 0.5 s
  retry/backoff (if any)       < 4.0 s
  DB commit/read model lag     < 1.0 s
  CI jitter allowance          < 2.0 s
  ------------------------------------
  chosen atMost                = 9-10 s
~~~

These numbers illustrate how to budget, **not a universal SLA for RabbitMQ**. Production tests should measure baseline/percentiles and set reasoned thresholds.

### Deadline and polling frequency are independent

A 10 s timeout with a 100 ms poll interval yields roughly up to 100 evaluations (depending on poll delay, callback duration, and scheduling). If the predicate is a heavy 500 ms DB query, setting poll to 10 ms will not make the test finish faster; it increases load, pool contention, and flakiness.

### Never increase timeouts endlessly

If a test fails because the consumer never started, the queue name is wrong, or the broker did not route, raising `atMost` from 10 s to 60 s only delays failure. Before raising deadlines, check the root cause:

- Did the producer publish to the right exchange/topic/routing key?
- Does the queue/topic actually exist?
- Is the listener container running/assigned?
- Did conversion/validation throw?
- Was the message requeued or sent to DLQ?
- Is the test polling the right datasource/tenant/event ID?
- Did the input fixture transaction commit so the consumer can see it?
- Is the state observer thread-safe?
- Is there resource starvation or connection pool exhaustion?

## 18. Managing RabbitMQ Testcontainers lifecycle

In the runnable project:

- `@Container static RabbitMQContainer broker`: container starts at **class scope** via the JUnit Testcontainers extension.
- `@DynamicPropertySource`: registers host, mapped AMQP port, username/password, and queue name into the Spring `Environment`.
- `@SpringBootTest` builds a full `ApplicationContext` using real RabbitMQ.
- `@DirtiesContext(AFTER_CLASS)`: prevents Spring's cache from keeping a connection factory/listener pointing to a stopped container.
- `@BeforeEach`: calls `AmqpAdmin.declareQueue` before publishing.
- Each test generates a unique `eventId`; no global `ProcessingLedger` reset is needed between methods.
- Ephemeral containers and auto-delete queues suit demos; never use production credentials or queues.

### Why a static container?

An instance `@Container` starts/stops per method, while Spring `ApplicationContext` normally caches across methods/classes. If the container changes host port between methods while `ConnectionFactory` stays bound to the old port, tests fail randomly with `Connection refused`.

A static container keeps a stable endpoint for the class. To share a container across multiple classes, align **lifetime with the context cache** and avoid letting the Testcontainers extension stop it while another cached context still uses it. Never copy a singleton container hack without understanding teardown and parallel semantics.

### Why a dynamic queue name?

If every CI job uses `orders.queue` on a shared RabbitMQ broker, messages mix and tests consume each other's events. In the lab, the queue name embeds a fresh per-class UUID to isolate resources. Even when Testcontainers gives each class its own broker, this remains a good protective habit before moving to shared test brokers.

### `@DirtiesContext` does not clean the broker for the test

`@DirtiesContext` makes Spring TestContext evict the cached context. It **does not delete committed/delivered messages**, does not replace DLQ cleanup, and does not clean external databases. Never use it as "magic cleanup" for all side effects.

## 19. Parallel tests: preventing races and state leakage

A Messaging suite can fail inconsistently because:

- Two test methods use the same `eventId`/`orderId`.
- One test drains a shared queue while another test waits for its message.
- One test resets a shared map/counter, wiping another test's state.
- A shared listener/executor pool is blocked for a long time by one test.
- Consumer group or queue names collide.
- A DB fixture is created in an uncommitted test transaction.
- One test stops/restarts the broker while another context still holds connections.
- An Awaitility predicate has side effects or reads non-thread-safe fields.
- Polling uses a repository with a stale `EntityManager` cache.

Mitigations:

1. Generate a distinct **correlation ID** per test.
2. Use thread-safe state or a committed DB read model.
3. Isolate brokers/queues/topics/consumer groups whenever possible.
4. Never reset global state when tests can run concurrently.
5. Ensure listeners hold no static mutable global state.
6. Separate business retries, publish retries, and test polling — never let polling re-trigger stimuli.
7. With multiple consumers, never assert total order unless the broker guarantees order under that exact partition/queue policy.
8. When resource locks are needed, use JUnit serialization/`@ResourceLock` per test module instead of `Thread.sleep`.
9. Never leak JPA sessions/JDBC connections inside conditions.
10. Clean up post-test resources using scoped keys, proper transactions, and container teardown.

### Why doesn't Awaitility eliminate all flakiness?

Awaitility eliminates **fixed sleeps and early assertion races**, yet cannot fix:

- Non-thread-safe state observers.
- Genuine system deadlocks.
- Brokers/containers restarting mid-test.
- Producers sending the wrong routing key.
- Assertions checking the wrong consumer group/datasource.
- Real external service failures.
- Timeouts set lower than valid environment latency.
- Business contracts lacking an observable completion point.

It gives tests **explicit deadlines and conditions**, while the overall integration harness design still determines final quality.

## 20. Error diagnostics: don't settle for just "condition timed out"

A useful QA diagnostic log on timeout should include:

~~~text
eventId=evt-...
queue=await.orders.<uuid>
expected=COMPLETED
observedState=UNSEEN / DECLINED / RETRYING / FAILED
deliveryCount=0/1/2...
effectCount=0/1/...
listenerRunning=true/false (if metrics available)
lastConsumerError=<sanitized type + message>
deadLetterCount=<if available>
elapsedMs=<observed>
~~~

This is a **diagnostic template**, not fixed stdout of the project. Never log message payloads containing PII, full credentials, tokens, or customer details.

### Diagnostic assertions with `untilAsserted`

~~~java
await()
    .alias("event " + eventId + " eventually completed")
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {
        assertEquals(COMPLETED, ledger.state(eventId),
                "state for eventId=" + eventId);
        assertEquals(1, ledger.effectCount(eventId),
                "unique effect count for " + eventId);
    });
~~~

Snippet uses `ledger`/imports from the project. On timeout, the final assertion failure reveals the actual state rather than just a boolean `false`. When reading failures, distinguish **condition wait timeout** from **broker connect timeout** — they happen at two different layers.

### `ConditionEvaluationListener` for tricky tests

Awaitility offers a condition evaluation listener to log state after each poll, helpful for debugging timing races:

~~~java
await()
    .conditionEvaluationListener(
        new ConditionEvaluationLogger())
    .atMost(Duration.ofSeconds(5))
    .until(() -> ledger.state(eventId) == COMPLETED);
~~~

This is an extension snippet needing `org.awaitility.core.ConditionEvaluationLogger` and matching variables. Do not enable per-poll logging across a whole suite of thousands of tests; CI logs will blow up. When needed, log only sanitized event IDs and states.

### Per-state deadlines

A multi-stage workflow might use:

~~~text
await QUEUED within 3s
await PROCESSING within 5s
await COMPLETED within 15s
~~~

However, if `PROCESSING` appears briefly and disappears before a poll, the test can fail even when the workflow succeeded. **Do not force waiting on every transient state** unless the contract truly requires observing them. Usually waiting for the **terminal business state** suffices.

## 21. Anti-patterns to avoid

### Anti-pattern 1: Fixed sleep

~~~java
Thread.sleep(5000);
assertEquals(COMPLETED, status(id));
~~~

Both slow and flaky. Replace with `await` using a deadline and condition.

### Anti-pattern 2: No deadline

~~~java
while (status(id) != COMPLETED) {
    // busy wait
}
~~~

The test can hang forever and burn CPU. Every integration test wait must be finite.

### Anti-pattern 3: No unique ID

~~~java
await().until(() -> totalProcessedCount() > 0);
~~~

If an old event was already processed by a prior test, the test passes immediately even when the current message was never consumed. Use exact correlation IDs.

### Anti-pattern 4: Checking only `QueueDepth == 0`

~~~java
await().until(() -> brokerQueueSize() == 0);
~~~

The message might be unacked, failed, or routed to the DLQ. An empty queue is not business success.

### Anti-pattern 5: Predicate with side effects

~~~java
await().until(() -> {
    rabbitTemplate.convertAndSend(queue, message);
    return status(id) == COMPLETED;
});
~~~

Every poll republishes the message. Separate publishing from waiting.

### Anti-pattern 6: Abusing `ignoreExceptions`

If a test ignores all exceptions, a repeated `SQLSyntaxErrorException` gets masked as a timeout, making debugging harder. Ignore only clear transient errors.

### Anti-pattern 7: Non-volatile flags

Worker sets a variable on thread A, JUnit polls on thread B, with no happens-before. Use concurrent collections/atomics/`volatile` or DB commits.

### Anti-pattern 8: Catching `ConditionTimeoutException` and passing

~~~java
try {
    await().atMost(Duration.ofSeconds(5))
        .until(() -> status(id) == COMPLETED);
} catch (ConditionTimeoutException ignored) {
    // DO NOT do this in a success test.
}
~~~

This is a **bad example**, do not copy. The test stays green even if the listener never processes anything. Only use `assertThrows` for cases **intentionally testing timeout behavior** like the sixth method in the lab.

### Anti-pattern 9: Mixing application retries with test polling

Awaitility retries **evaluating the condition**, not broker publishing. If the test publisher retries, the consumer retries, and the test callback also republishes, attempt counts become impossible to reason about. Apply the stimulus once and observe.

### Anti-pattern 10: Treating listener invocation as DB commit

If the listener calls a `@Transactional` service and throws before commit, invocation occurred yet data rolled back. Wait on committed database state when that is the contract.

### Anti-pattern 11: Uncommitted fixture transactions

JUnit `@Transactional` inserts an order row and publishes a message; the listener on another thread cannot see the row, causing a false timeout. Commit the fixture before sending.

### Anti-pattern 12: Raising timeouts whenever a test flakes

Never bump 10s to 120s before checking listener startup, routing, DLQ, thread safety, DB isolation, and logs. Timeouts should match SLAs, not hide bugs.

## 22. Comparing async HTTP testing with async Messaging testing

Both use Awaitility, yet at different boundaries:

- An async HTTP endpoint returning `202 Accepted` means the server accepted the request, not necessarily finished processing.
- A Messaging publish return/confirm means the producer/broker reached its milestone.
- With HTTP `202`, you can poll `GET /jobs/{id}` until `SUCCEEDED`.
- With Messaging, you can poll the database/read model by event ID until `COMPLETED`.
- When both systems use an outbox, distinguish job accepted, event published, consumer processed, and projection updated.

API polling example (illustrative):

~~~java
submitJob(jobId); // HTTP 202

await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() ->
        assertEquals("SUCCEEDED", api.readStatus(jobId)));
~~~

The goal is not "always poll": if a service returns a `CompletionStage` representing true completion, await the future rather than polling an endpoint; if it is an event stream, subscribe and verify events. **Choose the signal matching the observable contract.**

## 23. Diagnostic procedure when a Messaging test times out

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| Producer publishes yet event stays `UNSEEN` | Wrong queue/routing key, listener not ready | Inspect topology, listener startup, `RabbitAdmin` declarations |
| Consumer logs receipt yet condition fails | Wrong `eventId`/tenant or state observer | Check payload parsing/correlation, DB commit visibility |
| Event has state `FAILED`/`DECLINED` yet test keeps waiting | Terminal failure path | Add fail-fast or assert the right terminal outcome |
| `DeliveryCount=1, effectCount=0` | Handler unfinished or failed mid-way | Inspect listener stack traces, transactions |
| `DeliveryCount>1, effectCount>1` | Non-idempotent side effects | Add inbox key/unique constraint in DB |
| `QueueDepth=0` yet DB status wrong | Message unacked/in-flight/failed | Poll committed state instead of queue depth |
| Passes alone, fails in suite | Shared queue, state, container lifetime | Unique IDs/queues, lifecycle, context cache |
| Slow CI fails, laptop passes | Broker startup, CI CPU/IO load | Check timing metrics; pick realistic deadlines |
| Context fails before test | Docker/broker connection/credentials | Fix infrastructure; Awaitility hasn't run yet |
| Listener fails to start: missing queue | Wrong queue bean or declaration | Declare queue with matching name and flags; admin declare |
| Infinite requeue | Listener throws, default requeue | Configure retry/dead-letter; don't raise timeout |
| Kafka test fails because consumer unassigned | Consumer group setup/partition assignment | Wait for readiness, use isolated group |
| Database test reads stale data | Transaction snapshot/JPA cache/replica lag | Query committed state on matching connection |
| Timeout test passes even when worker died | Test caught and ignored exception | Never swallow `ConditionTimeoutException` |
| Negative test passes immediately yet event arrives later | Checked only a single instant | Use `during` or verify schedule contract |
| Tests take minutes | Fixed sleeps too long | Use early-terminating `await`, check scope |
| Polling overloads DB | `pollInterval` too small | Increase interval, optimize query, use indexes/test scope |
| Condition always true from stale data | Not filtered by event ID | Unique correlation key, fixture cleanup |
| Manual ACK causes unexpected redeliveries | ACK/NACK wrong tag or missing ack | Check ack mode/channel and broker protocol |
| Mockito timeout passes yet broker isn't running | Verified mock call without integration | Run real broker container |
| DLQ test fails | Missing DLX/binding/policy | Check topology, routing, and retry outcomes |

### Ordered debugging sequence

1. Identify the exact **event ID, producer, queue/topic, and consumer group**.
2. Verify the broker/container is running and connection config is right.
3. Verify the publisher routed to the right exchange/routing key.
4. Verify the listener container started and deserialized the payload.
5. Check listener exceptions/requeue/retry/DLQ.
6. Verify the input fixture transaction committed before publishing.
7. Verify the final business state committed and is observable from the test.
8. Verify correlation ID filtering rather than counting another test's events.
9. Check memory visibility or JPA cache staleness.
10. Compare deadline/poll frequency against valid retry/SLA bounds.
11. Diagnose context caching/parallel test interference.
12. Only after ruling out all of the above, adjust timeouts based on data.

## 24. Practice exercises

**Exercise A — remove Awaitility:** In `eventuallyCompletesMessageWithBoundedAwait`, replace `await` with an immediate assertion right after publishing. Run multiple times and explain the race condition. Revert.

**Exercise B — fixed sleep:** Replace `await` with `Thread.sleep(3000)` and measure suite duration. Compare with `await` when the listener finishes in tens of milliseconds.

**Exercise C — tiny deadline:** Set `atMost(Duration.ofMillis(1))` on the success test. Observe the failure and explain why the deadline fails to account for scheduling/CI.

**Exercise D — alias/diagnostics:** Add `alias("order "+eventId)` and multiple assertions inside `untilAsserted`, then observe the timeout message.

**Exercise E — correlation:** Replace per-`eventId` state with a single total `AtomicInteger`, and emit an older event from another test. Describe the risk of false passes.

**Exercise F — duplicate:** Remove `handledIds.add(eventId)` and always increment effects. The duplicate test must fail because `effectCount` becomes 2. Revert.

**Exercise G — decline:** Change the listener so `DECLINE` records `COMPLETED`. The business decline test must catch the bug.

**Exercise H — fail-fast:** In the terminal decline case, remove `failFast`. The test will wait until the deadline and throw `ConditionTimeoutException` instead of `TerminalFailureException`. Restore it for fast diagnostics.

**Exercise I — during:** Change the negative assertion from `during(350ms)` to an immediate single check. Explain why it fails to test an observation window.

**Exercise J — no publish:** Edit the expected-timeout test to actually publish an event, and observe `ConditionTimeoutException` no longer occurring. This proves the negative case is intentionally calibrated.

**Exercise K — RabbitMQ retry:** Add a listener branch that intentionally throws; configure bounded retries and a DLQ on an isolated test broker, asserting terminal DLQ state by `eventId`. Never allow infinite requeues.

**Exercise L — JDBC commit:** Replace the in-memory ledger with a Spring Data JDBC/JPA repository; have the listener update a row inside a transaction. Have Awaitility query from a fresh connection and assert committed state.

**Exercise M — `@Transactional` test:** Create an order fixture in an uncommitted test-managed transaction and publish. Analyze why the consumer thread cannot see the row; design committed fixture boundaries.

**Exercise N — Kafka:** Write a matching `KafkaListener` with a Testcontainers topic, publish an event, and await the DB projection. Never treat offset commit alone as business success.

**Exercise O — `CountDownLatch`:** Add a latch to the listener, try `countDown` at the start of the handler and then at the end. Analyze which placement truly represents the contract.

**Exercise P — transient states:** Create `QUEUED -> PROCESSING -> COMPLETED` states in a demo. Wait only on terminal `COMPLETED` to avoid missing short-lived intermediate states.

**Exercise Q — parallel:** Enable JUnit parallel execution using per-test UUID correlation. Ensure no method resets a global ledger/queue while another method is waiting.

**Exercise R — broken observer:** Change `ConcurrentHashMap` to an unsynchronized `HashMap` in a copy of the lab, and describe the data race/memory visibility bug. Never treat an occasional passing run as proof `HashMap` is safe.

## 25. Code review checklist for asynchronous Messaging tests

- [ ] Test awaits **business outcome**, not merely producer return or empty queue?
- [ ] Every `await` has a finite, reasoned `atMost`/deadline?
- [ ] Sensible `pollInterval`, no busy polling?
- [ ] Uses `untilAsserted` when multiple assertions are needed?
- [ ] Condition only reads state without publishing/mutating inside the polling callback?
- [ ] Each test uses its own `eventId`/`orderId`/correlation ID?
- [ ] Observer is thread-safe or queries committed database state?
- [ ] Listener invocation/ACK not confused with business transaction commit?
- [ ] If retries exist, timeout covers the retry contract without being overly broad?
- [ ] If terminal failures/DLQ exist, test fails fast or verifies negative outcomes?
- [ ] If testing "no event", uses a clear observation window/semantics rather than claiming forever?
- [ ] If testing duplicate delivery, asserts the business effect happened only once?
- [ ] Recognizes broker delivery can be at-least-once, not promising exactly-once without design?
- [ ] DB fixtures committed before publishing to another listener thread?
- [ ] Does not rely on test-managed `@Transactional` to roll back listener side effects?
- [ ] Testcontainers brokers/queues/consumer groups properly scoped?
- [ ] Spring `ApplicationContext` cache does not hold connections to stopped containers?
- [ ] Bounded retry/requeue/DLQ configured, no poison loops?
- [ ] Timeouts/failures provide diagnostic event ID, state, attempts, and queue?
- [ ] Test does not swallow `ConditionTimeoutException` in success cases?
- [ ] No secrets/sensitive payloads logged?
- [ ] CI has Docker/container runtime if running integration tests?
- [ ] Tests can run concurrently without resetting shared state or queues?
- [ ] Awaitility polling distinguished from application/publish retries?
- [ ] Assertions reflect API/DB/business contracts rather than deriving expected values from the SUT?
- [ ] Test reports prove JUnit methods executed, not just an `UP-TO-DATE` task?

## 26. Official References

The lesson selects **Spring Boot 3.3.5/Java 17** so examples have consistent imports and dependencies. Newer Spring AMQP/Awaitility/Testcontainers versions may change defaults and module naming; verify compatibility with the BOM of the project you are working on.

- [Awaitility — Usage (4.x)](https://github.com/awaitility/awaitility/wiki/Usage): `until`, `untilAsserted`, `atMost`, `during`, `pollInterval`, `failFast`, and thread-safety caveats.
- [Awaitility — Java API](https://www.javadoc.io/doc/org.awaitility/awaitility/4.2.2/): `ConditionFactory`, timeout exceptions, and polling.
- [Spring Boot 3.3 — AMQP](https://docs.spring.io/spring-boot/3.3/reference/messaging/amqp.html): `RabbitTemplate`, `@RabbitListener`, auto-declaring queues, and listener container factories.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): Rabbit listener containers, prefetch, concurrency.
- [Spring AMQP — Listener Container Properties](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `AcknowledgeMode.AUTO/MANUAL/NONE`, requeue, retry, and errors.
- [Spring AMQP — RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html): publishing, broker confirms/returns, and distinction from downstream consumer processing.
- [Spring AMQP — Enable Rabbit Listeners](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): `@EnableRabbit`, listener endpoint configuration.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): `RabbitMQContainer`, AMQP port mapping, and lifecycle.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): dynamic host/port and Spring test contexts.
- [Spring Framework — TestContext Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions and thread-scoped rollback limits.
- [JUnit Jupiter — Assertions](https://docs.junit.org/5.10.2/user-guide/): `assertThrows`, lifecycles, and test methods.

**Remember:** In Messaging, "the producer sent" and "the consumer completed business work" are distinct conditions. Create events with a **unique correlation ID**, publish **once**, wait for **business state/side effects** using `Awaitility.atMost(...).untilAsserted(...)`, and clearly separate retryable states from terminal failures. Finite deadlines keep tests from hanging; proper polling lets tests finish early; idempotency, transaction discipline, isolation, and diagnostics make QA results truly trustworthy.
