# Waiting for Listener Readiness Before Publishing in Spring Boot Messaging

## 1. Problem: the producer sends successfully yet the test sees no message

An integration test using Kafka, RabbitMQ, JMS, or another message broker typically follows these steps: start the Spring Boot context, send a message, and wait for the listener to process it. These steps are **asynchronous** relative to one another. A loaded Spring context does not mean the consumer has subscribed; a started broker does not mean the topic/queue is ready; a container reporting `isRunning()` does not necessarily have partition assignments or an active consumer attached to the broker.

A potentially unstable test example:

```java
// Anti-example: does not check whether the consumer has been assigned a partition.
kafkaTemplate.send("orders.events", "order-123").get();
assertEquals("order-123", inbox.poll(1, TimeUnit.SECONDS));
```

The above is only a **snippet**, not a standalone Java class. `send(...).get()` completing only confirms the Kafka producer received the send/ack result, **not** that the Spring `@KafkaListener` is ready or has processed the message.

If a fresh consumer starts with `auto.offset.reset=latest`, a message written **before the consumer gets its assignment and establishes its initial offset** can be skipped in the test. If the consumer already has committed offsets, behavior depends on those offsets instead. Using `Thread.sleep(3000)` after startup might hide the race on a laptop yet still flake in slow CI.

This lesson belongs to the **Messaging** group, topic **"Waiting for listener readiness before publishing"**. The focus is a **readiness gate before publishing**, rather than merely adding longer timeouts after publishing.

### After this lesson, you will know how to

1. Distinguish broker readiness, Spring context readiness, listener container startup, Kafka partition assignment, and business processing completion.
2. Use `KafkaListenerEndpointRegistry` to look up a container by `@KafkaListener(id=...)`.
3. Use `ContainerTestUtils.waitForAssignment(container, expectedPartitions)` from `spring-kafka-test` before sending messages.
4. Build a Java 17+ / Spring Boot **3.3.5** / Spring Kafka 3.2.x project with `@EmbeddedKafka`, a real producer, and a real listener.
5. Send messages via `KafkaTemplate` with producer confirmation, then wait with a time-bounded `BlockingQueue.poll(timeout)`.
6. Assert payload, key, partition, offset, and ordering within **a single Kafka partition**.
7. Avoid relying on `Thread.sleep`, `KafkaTemplate.send` results, `isRunning()`, or `ApplicationReadyEvent` as the sole readiness signal.
8. Handle multi-partition topics, concurrency, rebalances, multiple consumer groups, missing topics, disabled auto-startup, and context caching.
9. Recognize similar principles for RabbitMQ/JMS without applying Kafka APIs to other brokers.
10. Distinguish a listener receiving a record from committed side effects or successful business processing.

**Illustrative versions:** Java 17+, Spring Boot 3.3.5, Spring Kafka 3.2.x under Spring Boot dependency management. API details may differ in Boot 4 or Spring Kafka 4; do not assume these examples represent the latest release.

## 2. Five distinct layers of "ready"

```text
JUnit/Spring TestContext
  |
  | (1) ApplicationContext refreshed
  v
Kafka listener container created
  |
  | (2) Container isRunning() = true
  v
Kafka consumer thread starting / polling
  |
  | (3) Broker, topic, and group coordinator reachable
  v
Consumer assigned topic-partition(s)
  |
  | (4) ContainerTestUtils.waitForAssignment(...) succeeds
  v
Test producer sends message to Kafka
  |
  | (5) Kafka ACKs producer, then listener actually receives/processes
  v
Assert business behavior or received message
```

| Milestone | Question it answers | What it **does not** guarantee |
| --- | --- | --- |
| `@SpringBootTest` context created | Spring beans/config initialized | Consumer has an assignment |
| Kafka broker running | Kafka process/endpoint is up | Topic exists, group has joined |
| `container.isRunning()` | Listener container is in the running lifecycle state | Kafka consumer has been assigned partitions |
| Consumer started event | Consumer thread is about to poll | Specific assignment has completed |
| `waitForAssignment(container, 1)` | Container has the expected number of assigned partitions | Message was processed or business work committed |
| `KafkaTemplate.send(...).get(...)` | Producer received send result per Kafka ack policy | Listener processed the record |
| Listener receives record | Consumer code received payload | DB commit, external API side effect, downstream message succeeded |
| Assert business state | Expected application behavior is observable | All future retries/processing have settled |

In an example with a **single-partition** topic and a listener group with **one consumer**, the practical readiness condition is that the container has been assigned **one topic-partition**. With multiple partitions or multiple consumers in the same group, the expected partition count must match the topology rather than blindly hardcoding `1`.

## 3. Why is Thread.sleep not a readiness gate?

```java
Thread.sleep(2000);
kafkaTemplate.send(TOPIC, "order-1");
```

This is an **anti-example**. Two seconds might be enough on a developer laptop yet fail in CI when Kafka is electing leaders, broker metadata is slow, or consumer group rebalancing lags. Increasing it to 30 seconds slows down tests when the system was ready after 200 ms, while still proving nothing about readiness.

A **readiness gate** has sounder logic:

- Waits on a **meaningful infrastructure/domain condition**: consumer has partition assignments, queue has an active consumer, subscription is active.
- Has a **time limit** and fails clearly if the condition is never met.
- Proceeds immediately once the condition is met.
- Verifies message processing outcomes separately with an appropriate timeout.

In Spring Kafka, `ContainerTestUtils.waitForAssignment` waits for assignment with an internal timeout/exception. After sending, `BlockingQueue.poll(Duration)` or Awaitility lets the test wait for outcomes with a bounded timeout. Do not merge the two steps: readiness **before publishing**, outcome **after publishing**.

## 4. `KafkaListenerEndpointRegistry` and listener IDs

Spring Kafka registers listener containers created by `@KafkaListener` into a `KafkaListenerEndpointRegistry`. Annotation-created containers **are not necessarily ordinary beans** you can autowire directly by name; the registry is the proper management point.

```java
@Autowired
KafkaListenerEndpointRegistry registry;

MessageListenerContainer container =
        registry.getListenerContainer("orders-ready-listener");
```

In the listener:

```java
@KafkaListener(
    id = "orders-ready-listener",
    topics = "learning.ready.orders.v1",
    groupId = "orders-ready-group")
public void receive(String payload) {
    // Real message handling.
}
```

Both snippets above are illustrated fully in the project below. `id` identifies the container so the registry can look it up; `groupId` identifies the Kafka consumer group. **Do not equate the listener ID with the group ID**: they can coincide under framework defaults, yet this example sets them distinctly to avoid confusion.

### Do not assert only `isRunning()`

```java
assertTrue(container.isRunning());
```

This assertion is useful yet weak: the container may have just launched its consumer thread and still be waiting on metadata/group assignment. A Kafka listener can have no partitions yet even when `isRunning()` is true.

A more reliable check for the matching topology:

```java
assertTrue(container.isRunning());
ContainerTestUtils.waitForAssignment(container, 1);
```

`ContainerTestUtils` comes from `org.springframework.kafka.test.utils.ContainerTestUtils`. It waits until the container has the expected **assigned partition count**, throwing an exception if unmet per the version's behavior instead of sleeping arbitrarily and hoping.

**Limitation:** assignment shows the consumer group has been allocated Kafka partitions; it does not guarantee the handler is bug-free, the database is reachable, or side effects will commit. Hence you still must test message processing after publishing.

## 5. When can Kafka messages appear "lost" in tests?

Kafka is an append-only log, so in most cases the message is still on the broker. "Lost" here usually means **the test listener failed to read it** due to offset/group settings, or another consumer took it.

Example race sequence:

```text
T0: Spring context starts creating listener container
T1: Producer sends "order-123"
T2: Broker appends message (producer future SUCCEEDS)
T3: Consumer group completes assignment
T4: Consumer with auto.offset.reset=latest picks end of log
T5: Test waits for message and times out
```

This is one plausible scenario, not a claim that Kafka always skips early sends: if the consumer already has a committed offset or uses `earliest`, the record may still be read. It is precisely this dependence on offset and timing that makes tests unreliable.

### Can `earliest` replace `waitForAssignment`?

No. `spring.kafka.consumer.auto-offset-reset=earliest` helps when a fresh group **has no committed offsets**, but:

- It does not force the listener to finish starting up.
- It does not rewind a consumer that has already committed offsets back to the start of the log.
- It does not stop another consumer in the same group from taking partitions.
- It can cause tests to re-read stale messages if brokers/groups are reused.
- It does not replace asserting that the handler processed the message properly.

In the sample project, we combine `earliest` for predictable behavior on a fresh embedded broker **with** an explicit readiness gate so tests do not rely on offset reset to mask startup races.

## 6. Java 17+ / Spring Boot 3.3.5 project

The main project uses the **embedded Kafka broker** from `spring-kafka-test`, requiring neither Docker nor a locally installed Kafka server. It uses one topic, one partition, one listener, and one producer.

```text
kafka-listener-ready/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/messaging/
│   ├── MessagingApplication.java
│   ├── KafkaTopics.java
│   └── OrderEventListener.java
├── src/test/java/com/example/messaging/
│   └── OrderListenerReadyTest.java
└── src/test/resources/
    └── application-test.yml
```

### 6.1. settings.gradle

```groovy
rootProject.name = 'kafka-listener-ready'
```

### 6.2. build.gradle

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Dependency explanation:**

- `spring-boot-starter`: core Spring Boot application, no web server needed.
- `spring-kafka`: `KafkaTemplate`, `@KafkaListener`, Kafka listener containers.
- `spring-boot-starter-test`: JUnit Jupiter, Spring Boot test context, assertion support.
- `spring-kafka-test`: `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `ContainerTestUtils`, test utilities.
- `junit-platform-launcher`: supports running JUnit Platform in Gradle environments.

Spring Kafka/Kafka client versions are managed by the Spring Boot BOM. Do not arbitrarily force Spring Kafka 4.x into Boot 3.3.5 or mix mismatched Kafka test imports, as this can cause API/binary compatibility errors.

The demo **does not** include `org.testcontainers:kafka` or Docker; the Testcontainers section in section 16 is only an extension option.

### 6.3. MessagingApplication.java

`src/main/java/com/example/messaging/MessagingApplication.java`:

```java
package com.example.messaging;

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
```

`@EnableKafka` explicitly declares the intent to enable Kafka listener annotation support. Spring Boot also provides Kafka auto-configuration and supplies a default `kafkaListenerContainerFactory` when applicable; in this project there is no need to write a custom factory to test a simple String listener.

Production applications require a real `spring.kafka.bootstrap-servers` from configuration. **In tests**, `@EmbeddedKafka` injects the test broker endpoint into that property automatically without hardcoding `localhost:9092`.

### 6.4. KafkaTopics.java

`src/main/java/com/example/messaging/KafkaTopics.java`:

```java
package com.example.messaging;

public final class KafkaTopics {

    public static final String ORDERS =
            "learning.ready.orders.v1";

    private KafkaTopics() {
    }
}
```

The constant prevents topic name typos across the listener, test annotation, and producer. The example topic is created with **one partition**, so `waitForAssignment(container, 1)` matches. In real systems, partition counts are often managed by Kafka Admin/migrations rather than hardcoded in code.

## 7. Real listener and observation queue for the lesson

`src/main/java/com/example/messaging/OrderEventListener.java`:

```java
package com.example.messaging;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final BlockingQueue<ConsumerRecord<String, String>>
            observed = new LinkedBlockingQueue<>();

    @KafkaListener(
            id = "orders-ready-listener",
            topics = KafkaTopics.ORDERS,
            groupId = "orders-ready-group",
            concurrency = "1")
    public void receive(ConsumerRecord<String, String> record) {
        observed.offer(record);
    }

    public ConsumerRecord<String, String> awaitRecord(
            Duration timeout) throws InterruptedException {
        return observed.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public void clearObserved() {
        observed.clear();
    }
}
```

**Why use `BlockingQueue`?** `@KafkaListener` is called asynchronously on a consumer thread while the JUnit test runs on the test thread. `LinkedBlockingQueue` provides thread-safe handoff and `poll(timeout)` so the test waits for a **bounded** interval without busy loops or `Thread.sleep`.

**Architecture note:** the `observed` queue inside the listener is purely **lesson instrumentation** to inspect real Kafka records; it has no persistent business value and is not a pattern for a production event store. In real apps, the listener calls a service/repository, and integration tests assert database/state or mock a collaborator **behind the listener** (never mocking the listener itself).

### Why receive `ConsumerRecord` instead of just `String`?

`ConsumerRecord<String,String>` lets you verify:

- `record.topic()`: message came from the expected topic.
- `record.key()`: producer key was transmitted properly.
- `record.value()`: String payload deserialized properly.
- `record.partition()`: assigned partition.
- `record.offset()`: corresponding log offset.

With one partition, two records sent sequentially by the producer to the same topic/partition are delivered to the consumer in log order. If a topic has multiple partitions, **never** claim global ordering across them.

### Why not use a simple `CountDownLatch` for every test?

A `CountDownLatch` fits when you only need to count N callbacks, but once a latch reaches zero it **does not reset**. If the listener bean is cached across multiple test methods, a stale latch can let the next test PASS immediately before any new message arrives. You could create a fresh latch per test with thread-safe coordination, yet `BlockingQueue` in the example makes checking the **payload**/metadata and retrieving individual records easier.

`clearObserved()` is only for resetting test instrumentation between tests. In production, a test method should never clear internal state of a live user-serving service.

## 8. Dedicated Kafka producer/consumer config for tests

`src/test/resources/application-test.yml`:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
```

`@ActiveProfiles("test")` loads this file. It uses `String` serializers/deserializers on both sides so `KafkaTemplate` and `ConsumerRecord<String,String>` match. No `JsonDeserializer`, trusted packages, or custom message converter is needed for this String example.

**Do not put `spring.kafka.bootstrap-servers=localhost:9092` in the test file.** The embedded broker may pick a dynamic port; `@EmbeddedKafka(bootstrapServersProperty="spring.kafka.bootstrap-servers")` supplies the exact address.

`earliest` here makes the fresh broker test easier to understand, yet **does not replace the readiness wait**. If a broker has old data and the group has no offset, `earliest` could read excess records. The project uses a fresh embedded broker and dedicated topic per test class rather than shared Kafka data.

## 9. `@EmbeddedKafka` initializes the test broker

Before writing the full test, understand the annotation:

```java
@EmbeddedKafka(
        partitions = 1,
        topics = KafkaTopics.ORDERS,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers",
        kraft = true)
```

`@EmbeddedKafka` comes from `org.springframework.kafka.test.context.EmbeddedKafka` in `spring-kafka-test`. It creates a test-only broker with the listed topics and publishes its address into the property Boot reads.

**KRaft:** Spring Kafka 3.2.x supports KRaft mode for embedded Kafka via `kraft=true`. It avoids the legacy embedded broker's ZooKeeper dependency. Do not copy this option into very old Spring Kafka versions that lack that attribute.

**Not Docker:** embedded Kafka is a test broker managed by Spring Kafka test infrastructure inside the JVM/test runtime. It still has **asynchronous** startup and consumer group assignment; it is not a mocked `KafkaTemplate`. Hence tests still must wait for assignment.

### When is the broker created?

With `@SpringBootTest` and `@EmbeddedKafka`, the broker is registered in the Spring `TestContext` and bootstrap addresses are exposed to Spring Boot Kafka auto-configuration. Topics are created before the listener starts subscribing per the proper lifecycle. If a topic does not exist or has no leader, the container may start yet fail to receive assignments; timeouts surface the bug rather than failing silently.

### Why use `@DirtiesContext`?

The embedded Kafka broker and Spring `ApplicationContext` have interacting lifecycles/caches. `@DirtiesContext(classMode=AFTER_CLASS)` closes the context after the test class, reducing the chance of cached consumer clients pointing to a stopped broker when another test class runs. This has context startup cost, so use it deliberately rather than putting it on every unit test.

## 10. Runnable test suite: wait for assignment before sending

Create `src/test/java/com/example/messaging/OrderListenerReadyTest.java`:

```java
package com.example.messaging;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@EmbeddedKafka(
        partitions = 1,
        topics = KafkaTopics.ORDERS,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers",
        kraft = true)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderListenerReadyTest {

    @Autowired
    KafkaTemplate<String, String> producer;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    OrderEventListener listener;

    private MessageListenerContainer container;

    @BeforeEach
    void waitUntilListenerOwnsPartition() {
        container = registry.getListenerContainer(
                "orders-ready-listener");

        assertNotNull(
                container, "listener id must be registered");
        assertTrue(
                container.isRunning(),
                "listener container should auto-start");

        // One topic, one partition and one consumer in this test.
        ContainerTestUtils.waitForAssignment(container, 1);

        // Clear only test instrumentation, after readiness.
        listener.clearObserved();
    }

    @Test
    void listenerIsAssignedBeforeAnyPublication() {
        assertTrue(container.isRunning());

        var partitions = container.getAssignedPartitions();
        assertNotNull(partitions);
        assertEquals(1, partitions.size());
        assertEquals(
                new TopicPartition(KafkaTopics.ORDERS, 0),
                partitions.iterator().next());
    }

    @Test
    void messageSentAfterAssignmentIsConsumed()
            throws Exception {
        String marker =
                "order-one-" + UUID.randomUUID();

        SendResult<String, String> result = producer.send(
                KafkaTopics.ORDERS, "order-key-1", marker)
                .get(10, TimeUnit.SECONDS);

        assertEquals(
                KafkaTopics.ORDERS,
                result.getRecordMetadata().topic());

        ConsumerRecord<String, String> received =
                listener.awaitRecord(Duration.ofSeconds(10));

        assertNotNull(
                received, "listener did not receive message");
        assertEquals(KafkaTopics.ORDERS, received.topic());
        assertEquals("order-key-1", received.key());
        assertEquals(marker, received.value());
        assertEquals(0, received.partition());
    }

    @Test
    void twoMessagesOnOnePartitionPreserveOrder()
            throws Exception {
        String marker = UUID.randomUUID().toString();

        producer.send(
                KafkaTopics.ORDERS, "shared-key", marker + "-A")
                .get(10, TimeUnit.SECONDS);

        producer.send(
                KafkaTopics.ORDERS, "shared-key", marker + "-B")
                .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> first =
                listener.awaitRecord(Duration.ofSeconds(10));
        ConsumerRecord<String, String> second =
                listener.awaitRecord(Duration.ofSeconds(10));

        assertNotNull(first);
        assertNotNull(second);
        assertEquals(marker + "-A", first.value());
        assertEquals(marker + "-B", second.value());
        assertEquals(0, first.partition());
        assertEquals(0, second.partition());
        assertTrue(second.offset() > first.offset());
    }

    @Test
    void utf8PayloadIsDecodedAfterReadiness()
            throws Exception {
        String payload =
                "order-ready-utf8-"
                        + UUID.randomUUID();

        producer.send(
                KafkaTopics.ORDERS, "unicode-key", payload)
                .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> received =
                listener.awaitRecord(Duration.ofSeconds(10));

        assertNotNull(received);
        assertEquals(payload, received.value());
    }
}
```

**There are 4 `@Test` methods in the sample project**, each running `@BeforeEach` to verify readiness before sending data. No assertion depends on another test method running beforehand. Payloads use UUIDs to distinguish messages across cases.

### Reading each stage

**Stage 1 — locate listener**

`registry.getListenerContainer("orders-ready-listener")` must match the exact `id` on `@KafkaListener`. If the bean was not scanned or the listener ID is wrong, the result is `null`; the test fails immediately with a clear message.

**Stage 2 — check lifecycle**

`container.isRunning()` confirms auto-startup was triggered. This is a preliminary check, not complete readiness.

**Stage 3 — wait for partition assignment**

`ContainerTestUtils.waitForAssignment(container, 1)` waits for the consumer group to own the topic partition. If the container cannot join the group or the topic is missing, the test fails with an exception instead of waiting forever.

**Stage 4 — only then publish**

`producer.send(...).get(10, TimeUnit.SECONDS)` bounds the wait for the producer ack. It does not mean the listener has processed it, so the test still waits for the record in the queue.

**Stage 5 — verify listener callback**

`listener.awaitRecord(Duration.ofSeconds(10))` waits for real processing, then asserts topic, key, value, partition, or offset. If no record arrives, `assertNotNull` fails; the test never uses `Thread.sleep` to guess timing.

### Why split the two timeouts?

- Producer `get(10, TimeUnit.SECONDS)`: bounds broker send/ack.
- Consumer `poll(10 s)`: bounds event receipt from the listener.

If the producer fails, investigate broker/topic/network/serializer; if the producer ACKs yet the queue stays empty, investigate group assignment, listener invocation, deserializer, or handler failures. Two separate timeouts diagnose problems far more accurately than a single `Thread.sleep(20s)`.

## 11. How to run and expected results

With the Gradle Wrapper in the project:

```bash
./gradlew test --tests 'com.example.messaging.OrderListenerReadyTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the directory lacks a Gradle Wrapper yet has a compatible Gradle installed:

```bash
gradle test
```

The test class is designed with **4 `@Test` methods**. `spring-kafka-test` starts an embedded Kafka broker, so running it may take longer than pure Mockito tests. Local/CI environments need sufficient CPU, memory, and ability to create temp files/sockets.

**No execution report was collected in this lesson.** "4 methods" is the count from source code, **not a claim of 4 passing tests actually run**. After running locally, check:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

### Reliable output expectations

There is no fixed business stdout: Kafka/Spring/Gradle logs vary by version and environment. If all assertions pass, the Gradle `test` task exits cleanly; otherwise, test reports show whether failure occurred at startup, assignment, producer send, or listener receipt. Never hardcode a log line like `Assigned partitions: [topic-0]` as the sole expected output.

## 12. Why not only wait for `ApplicationReadyEvent`?

`ApplicationReadyEvent` means Spring Boot finished its startup sequence per Spring's lifecycle, yet Kafka group join/partition rebalance can still be running asynchronously. A handler such as:

```java
@EventListener(ApplicationReadyEvent.class)
public void publishWarmup() {
    kafkaTemplate.send("learning.ready.orders.v1", "hello");
}
```

is an **architectural anti-example snippet**, missing class and injection context. It does not prove `@KafkaListener` has received an assignment. If real business startup truly requires publishing after listeners are ready, use a **coordinator** tracking actual readiness or wait explicitly for assignment. Never copy test-only `ContainerTestUtils` into production simply because it is convenient.

### Production readiness differs from test readiness

In production, startup depends on brokers, topic creation, group membership, rebalances, and networking. Readiness checks can:

- Verify broker connectivity and topic metadata.
- Inspect listener container state/partition assignment.
- Distinguish listeners that are paused or stopped.
- Report readiness to orchestration (Kubernetes readiness probes) based on appropriate conditions.
- Handle timeouts/errors when the broker is temporarily unavailable, rather than blocking the bootstrap thread forever.

`ContainerTestUtils` is a **test-scope** utility (`spring-kafka-test` dependency). For production, use the registry and suitable state/metrics/health checks without depending on test artifacts at runtime.

## 13. `ConsumerStartedEvent` does not mean assigned

Spring Kafka emits application events related to listener lifecycle:

- `ConsumerStartingEvent`: consumer thread just initialized, before polling.
- `ConsumerStartedEvent`: consumer is about to start polling.
- `ConsumerFailedToStartEvent`: failed to start the consumer within the configured threshold.
- `ListenerContainerIdleEvent`: no messages received within a configured idle interval.
- `NonResponsiveConsumerEvent`: poll took too long / consumer unresponsive per monitoring rules.

These events aid startup observability and debugging, yet **do not confirm Kafka partition assignment**. A consumer can be started while a group rebalance is still in flight. When runtime proof of assigned partitions is required, inspect consumer rebalance callbacks, container assignment state, or matching metrics.

**Do not see a "consumer started" log and immediately publish** if the test requires ensuring the listener already owns the partition. In an embedded Kafka test, `waitForAssignment` is much closer to the target signal.

## 14. Why does a producer ACK not prove the consumer processed?

A Kafka producer can receive a broker ACK before the consumer has polled the record:

```text
Producer -> Broker appends record -> Producer ACK
                                  |
                                  v
                           Kafka partition log
                                  |
                       ... consumer polls later ...
                                  |
                                  v
                         @KafkaListener callback
                                  |
                                  v
                         Database / business side effect
```

`KafkaTemplate.send(...).get(...)` completing only speaks to the producer/broker stage under the configured `acks`. It does not wait for the listener, listener transactions, database commits, consumer offset commits, or downstream services.

To test end-to-end business behavior:

1. **Before sending:** wait for the listener to receive its assignments.
2. **After sending:** wait for an observable business side effect, such as a database row, order status, or output message.
3. Use a bounded timeout, never infinite polling.
4. If the handler retries or uses an async executor, wait for the real business condition, not just callback entry.
5. With DB transactions, never assert an uncommitted row from another test thread and assume the handler failed.

The `observed` queue in the project confirms callback receipt, **not business transaction commit**. In real systems, replace or supplement instrumentation with repository assertions or the state/event end users depend on.

## 15. Multiple partitions and concurrency

The sample project has a single partition, so:

```java
ContainerTestUtils.waitForAssignment(container, 1);
```

fits. With a three-partition topic and listener concurrency of two consumers in **one consumer group**, assignments are split across two child containers. The parent `ConcurrentMessageListenerContainer` normally aggregates the partitions of its children.

Conceptual example:

```text
Topic: orders.events = partitions [0, 1, 2]
Group: orders-group
Listener parent container concurrency=2

Child consumer A -> partitions [0, 2]
Child consumer B -> partition  [1]

Parent assignment total = 3
```

If the goal is **all three partitions owned by this listener container**, `expectedPartitions` is `3`. However, if another app/test consumer is in the same group, partitions may be assigned to that **other** consumer, and waiting for all three on one container will never succeed.

### Rules for choosing `expectedPartitions`

- Identify the topic(s) and actual partition counts.
- Identify listener concurrency.
- Identify **all consumers participating in the same group**.
- When the test controls the broker, topic, and sole group, you can expect the listener to receive all partitions.
- When a group has multiple instances, never assume one instance owns all partitions.
- Listeners using multiple topics/pattern subscriptions have different topologies; do not hardcode `1` when protecting all assignments.
- In specialized cases, wait for specific partitions via metadata/assignment state rather than inferring from `isRunning()`.

**Kafka only guarantees ordering within one partition**, with no global ordering across multiple partitions. The ordering test in this project places all records in a **single-partition** topic, so asserting increasing offsets is valid. With three partitions, use an appropriate key/explicit partition and assert per partition.

## 16. Alternative: real Kafka broker in Docker with Testcontainers

`@EmbeddedKafka` suits fast in-JVM tests, while Testcontainers is useful when testing closer to a specific Kafka broker image, Docker networking, or version compatibility.

Approach:

- Add `spring-boot-testcontainers`, `testcontainers:junit-jupiter`, and the Testcontainers Kafka module matching the BOM.
- Start a `@Container` Kafka container with an explicit lifecycle.
- With Spring Boot `@ServiceConnection` supporting the matching Kafka container, let Boot create `KafkaConnectionDetails` and configure bootstrap servers. If unsupported, use `@DynamicPropertySource` with `kafka.getBootstrapServers()`.
- Register or create topics via `KafkaAdmin`/`NewTopic` before waiting for assignment.
- **Still** look up `KafkaListenerEndpointRegistry` and call `ContainerTestUtils.waitForAssignment` before sending data.
- After sending, await listener processing with bounded assertions.
- Never accidentally connect to a localhost Kafka or someone else's broker.

Illustrative snippet (**not a standalone runnable project**, lacking Testcontainers dependencies/lifecycle):

```java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
}
```

The `kafka` variable here is a Kafka container created and managed properly in the Testcontainers test class. Key takeaway: **broker readiness is a necessary precondition, while assignment remains a separate condition**. A Kafka container reporting `isRunning()` does not mean the consumer group has joined.

If using `@ServiceConnection` for the broker, do not simultaneously register bootstrap servers via `DynamicPropertySource` without a clear reason; stick to one primary source of connection details to avoid precedence confusion.

## 17. Alternative: RabbitMQ listener readiness

With Spring AMQP/RabbitMQ, the concept is similar while the APIs differ from Kafka:

- The broker opening the AMQP port is not enough to have queues/bindings.
- A `@RabbitListener` container may be running yet not attached to a queue due to channel/connection/backoff.
- Queue declaration, exchange/binding setup, and consumer startup can occur asynchronously.
- Publisher confirms only prove the publisher/broker layer, not that a listener acked/processed the message.
- Use `RabbitListenerEndpointRegistry` to look up the listener container by ID, check lifecycle, and inspect **active consumer/readiness signals suited to the container type**.
- With `SimpleMessageListenerContainer`, active consumer counts are useful; with `DirectMessageListenerContainer`, consumers/queues are managed differently, so do not blindly cast one type to the other.
- Wait for processing outcomes with Awaitility, a latch, or a timed queue rather than `Thread.sleep`.
- When using `RabbitMQContainer`, wait for broker/container health, queue bindings, and active consumers before publishing.

Illustrative registry snippet (not standalone runnable source):

```java
RabbitListenerEndpointRegistry registry = ...;
MessageListenerContainer container =
        registry.getListenerContainer("invoice-listener");

// isRunning() is only a lifecycle signal;
// check active consumers/queue bindings separately.
```

`RabbitListenerEndpointRegistry` and `MessageListenerContainer` in this snippet belong to Spring AMQP, **not** Kafka classes. This guidance is a conceptual comparison, not a claim that Kafka's `ContainerTestUtils.waitForAssignment` works with RabbitMQ.

## 18. Alternative: JMS, Redis Streams, and message subscriptions

**JMS:** the listener container must be started, JMS connection/session/subscription created, and the broker ready. `DefaultMessageListenerContainer.isRunning()` is a first step; durable subscriptions or destination creation may require separate verification. Sending before a consumer subscribes behaves differently between queues and topics, especially non-durable topics.

**Redis Streams consumer groups:** require the stream to exist, the group created at the right offset, and the consumer active/read path working. Do not confuse `XADD` with `XREADGROUP` having consumed. Pick offset `0`, `$`, or group-delivered pending semantics per contract.

**Pure pub/sub:** if a subscriber has not subscribed when a publisher emits a message, the message can **genuinely be lost** because there is no durable log/queue, unlike Kafka. Waiting for subscription ack/readiness before publishing is even more critical.

**Mocked message broker:** a test using only a mocked producer does not test listener readiness. Only when a real broker and consumer run can startup races be caught.

## 19. When a listener has `autoStartup=false`

Some apps disable auto-startup because a listener should run only after migrations or manual enabling:

```java
@KafkaListener(
    id = "orders-ready-listener",
    topics = KafkaTopics.ORDERS,
    autoStartup = "false")
public void receive(String payload) {
    // ...
}
```

This is a **variant snippet**, not applied to the main runnable project. With `autoStartup=false`, `container.isRunning()` is false. When a test is supposed to explicitly start the listener:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-ready-listener");
assertNotNull(container);
container.start();
ContainerTestUtils.waitForAssignment(container, 1);
```

Provide proper cleanup/stop if the test controls lifecycle manually. **Never call `waitForAssignment` on a container intentionally left unstarted** and expect it to start on its own. In production, delayed startup may come with separate ordering/migration/business readiness constraints.

If the app has many listeners, starting/stopping the entire registry has broad impact; managing listeners by exact ID is usually better.

## 20. Group rebalances change readiness

Assignment is not a permanent state. When a consumer joins, dies, partition counts change, or broker/network issues occur, Kafka can **rebalance**:

```text
Listener assigned partition -> test begins publish
          |
          +-- new consumer joins same group
          |
          v
Rebalance starts: assignment may be revoked
          |
          v
New assignment to this or another consumer
```

`waitForAssignment` protects against startup races in tests that control the broker and group, yet **does not** prove no rebalance happens after it returns. To keep tests reliable:

- Use isolated group IDs and topics for the suite.
- Do not run other tests against the same group and broker without parallel design.
- Avoid starting/stopping consumers arbitrarily within the same test.
- With multi-consumer topologies, design expected assignments appropriately instead of "waiting for all partitions on one consumer".
- If you want to test rebalances, make that **a separate integration test**: observe listener state before/after revoke/assign and verify no duplicates/losses outside the contract.

In production when rebalances actually happen, message processing must have idempotency and a sound offset commit strategy; readiness waits do not replace them.

## 21. Choosing the right ack mode, offsets, and isolation

Several Kafka settings easily make tests behave differently from expectations:

| Setting | Meaning | Impact on tests |
| --- | --- | --- |
| `auto.offset.reset=earliest` | If group has no committed offset, start at earliest | Can read old records on reused brokers |
| `auto.offset.reset=latest` | If group has no committed offset, start at end of log | Messages sent before assignment may be skipped |
| `group.id` | Consumer group identity | Different groups read the log independently; consumers in the same group split partitions |
| `enable.auto.commit` | Whether the Kafka client auto-commits offsets | Differs from listener/container commit strategies |
| Spring listener ack mode | When the framework acknowledges/commits | Not equivalent to a business DB transaction commit |
| `isolation.level=read_committed` | Skips uncommitted/aborted transactional records | Transactional producer tests need matching config |
| Topic partition count | Record distribution and ordering | Affects expected assignments and message order |

Never set `auto-offset-reset=earliest` just to "make all tests pass" if production requires `latest`/committed positions. First diagnose the race condition, then write a readiness gate and isolate data/group IDs. If a test specifically verifies **offset reset behavior**, intentionally sending before assignment may be a valid setup, though that is not a normal listener-ready test.

### Producer keys do not determine cluster-wide order

Within a single partition, records have log order. A stable key normally lets the partitioner send same-key messages to the same partition, yet **multi-partition topics and partition-count changes** can affect mapping. When a test requires strict ordering, choose one partition or send explicitly to the same partition and assert offsets. The sample project uses one partition to eliminate ambiguous assumptions.

## 22. Bounded waiting and failure diagnostics

A useful wait must have a **deadline**. In the project:

```java
ContainerTestUtils.waitForAssignment(container, 1);
```

This test utility performs a bounded wait and throws when assignment is not reached. If it fails, investigate the root cause/lifecycle rather than immediately replacing it with `Thread.sleep(60000)`.

To wait for business side effects, you can use Awaitility (outside the project, requires adding the dependency) like:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertEquals("PROCESSED", repository.findStatus(id)));
```

This is a **snippet** without `repository`/`id` or the Awaitility dependency in `build.gradle`. It illustrates waiting for an eventual condition instead of fixed sleeps.

### Which logs help debugging?

On timeout, selectively gather:

- Listener ID and `container.isRunning()`.
- Assigned partitions at the time of failure.
- Topic name and topic partitions (watch for typos).
- Actual consumer group ID.
- Bootstrap servers (never log passwords/secrets).
- Kafka startup, group join/rebalance logs.
- Producer send exception/result metadata.
- Consumer deserialization/handler exceptions.
- Offset reset policy and committed offsets when relevant.

Never paste raw Kafka logs containing PII payloads, credentials, or SASL settings into public artifacts. Test error messages should distinguish **waiting for readiness vs. waiting for message processing**.

## 23. Avoiding test pollution and order dependency

Reasons an individual test PASSES yet the full suite FAILS:

- Sharing brokers/topics/groups across multiple test classes.
- Combining `@EmbeddedKafka` and a global embedded broker, causing system property conflicts.
- Context cache holding consumers pointing to a stopped broker.
- One test restarting a listener so the next test sees altered state.
- Test queue/latch not reset or retaining stale records.
- Producer sends 2 records yet the test only polls 1, leaving "leftovers" for the next test.
- Parallel tests sending to the same topic/consumer group and stealing each other's messages.
- Starting a test before group assignment stabilizes.
- Tests asserting global order across multiple partitions.

The sample project uses one embedded broker/class, one topic/group, four sequential methods per JUnit default, readiness before publishing, queue resets, and exact record draining. If JUnit parallel execution is enabled, isolate test topics/groups/fixtures or restrict parallelism on this class; **do not** assume a shared queue remains safe.

### Context cache and `@DirtiesContext`

`@DirtiesContext(classMode=AFTER_CLASS)` closes the Spring test context after the class, reducing lifecycle mismatch risks. If multiple Kafka tests share brokers or Testcontainers, design clear ownership/lifecycles across the suite. Never run a listener on broker A alongside a `KafkaTemplate` pointing at broker B.

## 24. Common errors and solutions

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| `registry.getListenerContainer(...) == null` | Wrong ID, bean not scanned, or `@KafkaListener` not registered | Check ID, `@EnableKafka`, component scan |
| `container.isRunning()==false` | `autoStartup=false`, startup error, context unready | Check lifecycle/exceptions; call `start()` if test-controlled |
| `waitForAssignment` times out | Missing topic, broker not ready, group cannot join, consumer crashing | Check Kafka logs, topic metadata, group ID |
| Assigned count lower than expected | Another consumer in the same group owns partitions | Isolate group or adjust expected count for topology |
| Producer send ACKs yet test receives nothing | Listener unassigned, offset reset, deserializer, or different consumer group | Wait for assignment before sending; check errors |
| Passes locally, fails in CI | Different startup timing/resources | Avoid fixed sleeps, use bounded waits and adequate CI resources |
| Test sees previous case's message | Shared queue/topic/group, undrained records | Unique markers and cleanup/isolation |
| Test reads record yet DB lacks row | Async handler/transaction uncommitted | Wait for business state, not just callback |
| Ordering test fails on multi-partition topic | Kafka only orders per partition | Send to same partition, assert per partition |
| `@EmbeddedKafka` fails to start | Dependency/version/port/temp files | Check `spring-kafka-test` and logs |
| Consumer fails to decode String | Mismatched serializer/deserializer | Configure `String` serdes in test YAML |
| Missing `KafkaTemplate` bean | Missing `spring-kafka`/auto-config | Check Gradle and Spring Boot Kafka config |
| Unknown topic or partition | Topic not created or name mismatch | `@EmbeddedKafka` topics, `KafkaAdmin`/`NewTopic` |
| `ConsumerStartedEvent` fired yet nothing received | Event does not guarantee assignment | Use `waitForAssignment` |
| Rabbit listener `isRunning` yet not consuming | Queue/binding or active consumer not ready | Check active consumers/connection separately |
| Hangs forever | Await missing deadline | Use bounded poll/await timeouts |
| Flaky parallel jobs | Shared groups/topics | Isolate per suite, avoid consumer competition |
| App hits production broker | Wrong bootstrap server config | Use embedded property or Testcontainers connection details |

### 7-step debugging roadmap

1. Identify which broker the test actually uses: embedded, container, or shared?
2. Confirm the topic exists with the expected partition count.
3. Confirm the listener bean was scanned by Spring and found in the registry by exact ID.
4. Confirm the container is running and the Kafka consumer received its assignment.
5. Only then send a record with a unique marker; await the producer future with a timeout.
6. Await the listener outcome with a timeout; verify key/value/topic/offset or business state.
7. If it fails only in the full suite, check group collisions, reused brokers, parallel execution, and context caching.

## 25. Pre-merge QA checklist

- [ ] Distinguished context refresh, broker ready, listener running, partition assigned, and handler completed?
- [ ] `@KafkaListener` has an explicit ID for registry lookup?
- [ ] `getListenerContainer(id)` checked for non-null?
- [ ] Container started under proper lifecycle; `autoStartup` understood?
- [ ] For Kafka, test **waits for assignment** before publishing?
- [ ] Expected partition count matches topic/group topology?
- [ ] No fixed `Thread.sleep` used instead of a readiness gate?
- [ ] Producer send has a timeout and checks result/exception?
- [ ] Test awaits listener/business outcome with bounded poll/await?
- [ ] Producer ACK not treated as listener completed?
- [ ] Kafka serializers/deserializers match payload type?
- [ ] Broker bootstrap URI comes from embedded/Testcontainers, not hardcoded localhost?
- [ ] Topic created before listener subscribes?
- [ ] Consumer group/topic isolated from other tests?
- [ ] `auto.offset.reset` and committed offsets handled properly?
- [ ] If testing ordering, records belong to the same partition?
- [ ] No global ordering asserted across multi-partition topics?
- [ ] Test hooks/queues/latches do not leak state between methods?
- [ ] No test depends on JUnit method execution order?
- [ ] CI has sufficient resources for embedded Kafka/Testcontainers?
- [ ] Spring context cache and broker lifecycle aligned?
- [ ] Kafka `waitForAssignment` API not blindly applied to Rabbit/JMS?
- [ ] Business side effects verified separately if required?
- [ ] Checked actual execution reports rather than inferring PASS from source code?
- [ ] Sensitive payloads or secrets excluded from test artifacts?

## 26. Practice exercises

1. Run `OrderListenerReadyTest` and observe how the Kafka listener gets assigned a partition before publishing.
2. Temporarily remove `ContainerTestUtils.waitForAssignment` in a sandbox, enable `auto-offset-reset=latest`, and run repeatedly to observe instability; do not promise the race reproduces on every single run.
3. Change the listener `id` while keeping the old lookup ID in the test, and see the assertion report the missing container.
4. Set `autoStartup="false"` and explain why `start()` must be called before waiting for assignment.
5. Remove `@EnableKafka` while using Boot auto-config, verify whether the listener still registers and why; do not assume all app configs behave identically.
6. Change the Kafka topic to three partitions, set `concurrency=2`, and pick the matching expected assignment.
7. Create another consumer in the same group in another test, observing consumer competition and rebalance.
8. Send two messages with the same key on a two-partition topic and explain the ordering guarantee's scope.
9. Send Unicode data and verify `StringSerializer`/`StringDeserializer` handle it accurately.
10. Switch the consumer deserializer to JSON against a String payload and inspect the root cause instead of extending timeouts.
11. Make the producer timeout too short in simulated CI and distinguish producer failure from listener timeout.
12. Add a real service/repository to the listener and use Awaitility to await DB state after the callback.
13. Use `@EmbeddedKafka(kraft=true)` and check which Spring Kafka versions support that attribute.
14. Add Testcontainers Kafka to compare a real broker image against embedded; still wait for assignment separately.
15. Write a RabbitMQ test checking active consumers before publishing; do not use Kafka `ContainerTestUtils` for Rabbit.
16. Run parallel test classes sharing a group to see why tests need isolated consumer groups/topics.
17. Use `ConsumerStartedEvent` as the sole signal in a sandbox and analyze why it is insufficient.
18. Run a single test alone and the full suite; prevent leftover messages from other tests.
19. Inspect JUnit XML/HTML reports to verify real PASS/FAIL/SKIPPED test counts.
20. Design a production readiness strategy when listeners can rebalance after startup.

## 27. References

- [Spring Boot 3.3 — Kafka Support](https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html): auto-configuration, `KafkaTemplate`, `@KafkaListener`, testing with embedded broker.
- [Spring Kafka 3.2 — Testing Applications](https://docs.spring.io/spring-kafka/reference/3.2/testing.html): `spring-kafka-test`, `@EmbeddedKafka`, KRaft, embedded brokers, and utilities.
- [Spring Kafka 3.2 — ContainerTestUtils](https://docs.spring.io/spring-kafka/docs/3.2.x/api/org/springframework/kafka/test/utils/ContainerTestUtils.html): `waitForAssignment(Object, int)` and failure modes.
- [Spring Kafka — @KafkaListener Lifecycle](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/kafkalistener-lifecycle.html): registry, listener IDs, and container startup.
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): consumer started/idle/non-responsive events and their meanings.
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): group ID, `auto.offset.reset`, isolation level.
- [Testcontainers Java — Kafka](https://java.testcontainers.org/modules/kafka/): Kafka container bootstrap addresses.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): Rabbit listeners, consumer lifecycle.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@BeforeEach`, test independence.
- [Spring Framework — TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): application context reuse.

## 28. Conclusion

**Waiting for listener readiness must rely on the right condition — not sleep durations.** In Kafka integration tests, Spring application startup and `container.isRunning()` do not guarantee the consumer has partition assignments. A simple, well-scoped strategy when the test controls the broker/topic/group is:

1. Look up the container via `KafkaListenerEndpointRegistry.getListenerContainer(listenerId)`.
2. Confirm the container is running and call `ContainerTestUtils.waitForAssignment(container, expectedPartitions)`.
3. Only **after that**, send records using `KafkaTemplate`.
4. Wait for the listener callback or business state using a bounded timeout.
5. Assert payload/metadata/side effects and keep fixtures/groups/topics isolated across tests.

Broker ACK does not mean processing is complete, `auto.offset.reset=earliest` does not replace readiness, and Kafka ordering is guaranteed only within each partition. When working with RabbitMQ, JMS, or Redis Streams, apply the same mindset around subscription/consumer readiness while choosing **each broker's own mechanism**. Actual test validation should inspect Gradle/CI reports before claiming PASS.
