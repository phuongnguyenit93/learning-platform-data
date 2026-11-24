# Embedded Kafka and Kafka in Testcontainers

## 1. Goal: how far should Kafka testing go?

In Spring Boot, a business workflow typically uses `KafkaTemplate` to send events and `@KafkaListener` to consume events asynchronously. A simple test with Mockito can confirm that the `send` method was called, but it does not run the Kafka protocol, create records in a topic, or execute a consumer. Therefore, a test that only verifies mocks **fails to catch** wrong bootstrap servers, topics, serializers, consumer groups, partition assignments, or listeners that failed to register.

There are two ways to run a real Kafka broker in tests:

- **Embedded Kafka:** the `spring-kafka-test` module runs a broker inside the test environment, configured with `@EmbeddedKafka`. No Docker is needed in typical setups.
- **Kafka Testcontainers:** the Testcontainers module runs Kafka in a Docker-compatible container using the specified broker image/version. Spring Boot can obtain bootstrap servers from `@ServiceConnection`.

The two approaches do not completely replace each other. Embedded Kafka suits relatively lightweight Kafka integration tests. Kafka Testcontainers suits verifying client compatibility against a containerized Kafka image and composing multiple services in the same environment. Both are usually **single-broker tests** and do not by themselves prove availability, replication, security, or production cluster performance.

### What you will learn

1. Distinguish unit tests, Kafka broker integration tests, and infrastructure/cluster tests.
2. Understand that producer acknowledgment differs from listener/business processing.
3. Use `@EmbeddedKafka(kraft=true)` in Spring Kafka 3.3.
4. Use `ConfluentKafkaContainer` with Testcontainers 1.21.x and Spring Boot 3.5's `@ServiceConnection`.
5. Create topics with `NewTopic`/KafkaAdmin, and wire `KafkaTemplate` and `KafkaListener` via test configuration.
6. Wait for the listener to receive partition assignments, avoiding `Thread.sleep` that causes flaky tests.
7. Verify record key/value, Unicode, correlation headers, topic, partition, and offset.
8. Verify message ordering **within the same partition**, without inferring global order.
9. Design tests properly around consumer groups, offsets, retries, DLT, and Kafka transactions.
10. Run a Java 17+ example containing **7 JUnit Jupiter tests** using the same production code against two different brokers.

**Version scope:** the example targets **Java 17+, Spring Boot 3.5.x, Spring Kafka 3.3.x, and Testcontainers 1.21.x**. On this branch, Boot manages `spring-kafka` and Testcontainers via its BOM. For Spring Boot 4, Spring Kafka 4, or Testcontainers 2, review imports/packages, dependency coordinates, and broker compatibility.

## 2. Map of testing layers

```text
Order business service
        │
        ▼
OrderEventPublisher (KafkaTemplate)
        │
        ▼
Kafka producer + serializer
        │
        ▼
  Kafka broker (topic, partition, offset)
        │
        ▼
Kafka consumer + deserializer
        │
        ▼
OrderEventReceiver (@KafkaListener)
        │
        ▼
Business processing / database / downstream
```

| Layer | Tool | What stays real? | What is not verified |
|---|---|---|---|
| Unit | Mockito/fake event port | Business rules, publish decisions | Broker, serializer, listener, offsets |
| Embedded Kafka | `spring-kafka-test` | Kafka client + broker + listener | Container image, production network |
| Kafka container | Testcontainers Kafka | Client + broker in Docker image | Multi-node replication, TLS/ACL unless configured |
| Cluster fault test | Multi-broker/test environment | Leader changes, replication, failover | All production conditions |
| Staging/smoke | Permitted Kafka infrastructure | Auth, network, deployment topology | Always fast/isolated tests |

**Selection rule:** mock at the highest boundary that does not lose the behavior you need to verify. To test Kafka message formats and listener callbacks, you need a real broker. To test business branching, you do not need to start Kafka. To test inbound HTTP/controllers, you must test the MVC/HTTP layer separately; a broker test does not automatically test inbound APIs.

## 3. What is Embedded Kafka?

`org.springframework.kafka:spring-kafka-test` provides `EmbeddedKafkaBroker`, `@EmbeddedKafka`, `KafkaTestUtils`, and `ContainerTestUtils`. With a Spring TestContext such as `@SpringBootTest`, the annotation can register a broker bean in the context. Producers/consumers use real Kafka client APIs, only swapping the Kafka bootstrap destination to the broker started for the test.

### 3.1. KRaft and ZooKeeper in Spring Kafka 3.3

Spring Kafka 3.3 has two implementations for the embedded broker:

- `EmbeddedKafkaZKBroker`: legacy implementation using ZooKeeper.
- `EmbeddedKafkaKraftBroker`: uses KRaft, enabled with `kraft=true`.

Example preferring KRaft:

```java
@EmbeddedKafka(
        kraft = true,
        partitions = 2,
        topics = "orders.events.embedded",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

This is an annotation snippet; the full test is in section 9. In modern Kafka, KRaft replaces ZooKeeper; newer Spring Kafka versions may remove ZooKeeper configuration. Do not copy Spring Kafka 3.3 code into Spring Kafka 4 without reading the new API.

### 3.2. Bootstrap property

Spring Boot reads the Kafka address from `spring.kafka.bootstrap-servers`. Embedded Kafka starts a broker on a test port and can export its address into this property via `bootstrapServersProperty`. In Spring Kafka **3.0.10+**, the default mapping target is also `spring.kafka.bootstrap-servers`; declaring it explicitly avoids confusion with older docs that only used `spring.embedded.kafka.brokers`.

Changing only the bootstrap property **does not automatically fix** custom `ProducerFactory`/`ConsumerFactory` beans built programmatically without reading the Spring `Environment`. The example in this lesson uses Boot auto-configuration so all clients use the test broker.

### 3.3. Strengths and limitations

Embedded Kafka requires no Docker and often fits CI environments without a container runtime. It verifies the producer/consumer path, Kafka topics, and listener wiring. However, the broker is packaged inside the test runtime and does not represent a Kafka container image, external Docker networking, ACL/TLS, or a multi-broker cluster.

Spring Kafka supports a global JUnit-plan broker, but warns **not to mix a global embedded broker with per-class `@EmbeddedKafka`** carelessly: they share system properties and can cause clients to connect to the wrong broker. Use dedicated test topics and manage broker lifecycles explicitly.

## 4. What is Kafka in Testcontainers?

Testcontainers runs a Kafka broker using a Docker image, automatically managing container startup, mapped host ports, and cleanup. For Testcontainers **1.21.x**, the appropriate classes are:

- `org.testcontainers.kafka.ConfluentKafkaContainer`, using `confluentinc/cp-kafka` images 7.4.0 and newer.
- `org.testcontainers.kafka.KafkaContainer`, using Apache Kafka images compatible with the module.
- The legacy class `org.testcontainers.containers.KafkaContainer` is deprecated and should not be used in new code.

Example using Confluent:

```java
@Container
@ServiceConnection
static final ConfluentKafkaContainer KAFKA =
        new ConfluentKafkaContainer(
                "confluentinc/cp-kafka:7.8.0");
```

This is a snippet inside a class annotated with `@Testcontainers` and `@SpringBootTest`. The image/version must be allowed in CI and the Docker runtime must be running.

### 4.1. @ServiceConnection in Boot 3.5

The `org.springframework.boot:spring-boot-testcontainers` dependency provides `@ServiceConnection`. When Spring Boot detects a typed Kafka container, Boot creates `KafkaConnectionDetails` for auto-configured Kafka clients. **Connection details take precedence over connection properties in `application.properties`**.

This mechanism is better than hardcoding `localhost:9092` because Testcontainers exposes Kafka on a random mapped port. For clients running inside another container, do not blindly use host loopback addresses; Kafka advertised listeners may need to be configured for the Docker network.

### 4.2. @DynamicPropertySource as an alternative

When not using `spring-boot-testcontainers` or when manual configuration is needed:

```java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.kafka.bootstrap-servers",
            KAFKA::getBootstrapServers);
}
```

This is **alternative illustrative code**, requiring the proper imports and container lifecycle. The main test in this lesson uses `@ServiceConnection`; do not stack both wiring mechanisms for the same address to avoid confusion over precedence.

### 4.3. Docker dependencies and limitations

Testcontainers requires a Docker daemon or compatible runtime, permission to pull images, sufficient CPU/RAM/disk, and working loopback/container networking. A single-node Confluent image **does not represent** a multi-node Kafka cluster. The PLAINTEXT image in the sample also does not verify production TLS/SASL/ACL.

In the Spring Boot 3.5 BOM, the Testcontainers module uses the artifact `org.testcontainers:kafka` from the **1.21.x** line. Testcontainers 2.x docs may use `org.testcontainers:testcontainers-kafka`. Mixing artifacts from two major lines without controlling versions typically causes build errors.

## 5. Comparing Embedded Kafka and Testcontainers

| Criterion | Embedded Kafka | Testcontainers Kafka |
|---|---|---|
| Docker required | No | Yes |
| Real broker | Yes | Yes |
| Real Kafka producer/consumer | Yes | Yes |
| JUnit setup | `@EmbeddedKafka` | `@Testcontainers/@Container` |
| Bootstrap | `bootstrapServersProperty` | `@ServiceConnection` |
| Broker version | Follows test library/Kafka dependencies | Follows Docker image tag |
| Closeness to deployment image | Lower | Higher |
| CI startup/resources | Usually lighter | Usually heavier |
| Topics, groups, offsets | Verifiable | Verifiable |
| Kafka serializers/headers | Verifiable | Verifiable |
| Listener assignment/rebalances | Yes | Yes |
| Host↔container networking | No | Yes |
| Multi-node failover by default | No | No |
| TLS/SASL/ACL by default | No | No |
| Production scale/load performance | Not proved | Not proved |

**Guidance:** unit tests for business logic; Embedded Kafka for fast integration; Testcontainers for broker image compatibility and multi-service environments; multi-node/fault suites for distributed behavior.

## 6. Kafka semantics to understand before asserting

### 6.1. Producer ACK is not consumer success

Spring Kafka 3.x `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K,V>>`. When the future completes, the producer has received the result per `acks` and broker metadata. This does not mean the listener finished processing, the Kafka consumer offset was committed, or the database was written.

A minimal end-to-end test must:

1. Send a record via a real `KafkaTemplate`.
2. Await the future with a timeout and check metadata.
3. Wait for the listener to receive the record via an observable signal.
4. Assert key, value, topic/partition/offset, or business side effects.

If the listener also writes to a DB or calls HTTP, you must verify the **business outcome**; the queue test in the example only observes the callback and does not claim DB integration.

### 6.2. Partition ordering

In Kafka, records have increasing offsets within **one partition**. Kafka does not guarantee global ordering across partitions. If ordering is required for an aggregate such as an order, use a consistent key and an appropriate producer partitioning policy.

The lesson's test sends two records with the **same key**; after the first record's future completes, it sends the second record, then asserts:

- Same partition.
- Second record's offset is greater than the first record's offset.
- The listener observes the event values in order.

Do not extend this conclusion to two different keys or multi-partition global ordering.

### 6.3. Consumer group and offset reset

A consumer group stores committed offsets. `spring.kafka.consumer.auto-offset-reset=earliest` is only used when there is **no valid committed offset** for the group/partition; it does not automatically rewind a group that has already committed.

You should:

- Use a separate group ID per test class or per run if sharing a broker.
- Use a separate topic when multiple tests run concurrently.
- Not share the same group between a "probe consumer" and the application's listener if both should receive all records.
- Wait for assignment before sending; do not merely `Thread.sleep`.
- Not let an old consumer read records from a previous test that a new test mistakes for its own event.

Spring Kafka test utilities provide `KafkaTestUtils.consumerProps(...)` and record-fetching methods, though an independent consumer still needs a clear group/offset policy.

## 7. Runnable example: one app, two test Kafka brokers

The example uses **Java 17+, Spring Boot 3.5.x, Spring Kafka 3.3.x, and Testcontainers 1.21.x**. One production app has a real publisher/receiver/config. Two test classes use that exact same source code:

- `EmbeddedKafkaIntegrationTest`: 3 JUnit tests, in-process test broker, **no Docker**.
- `KafkaTestcontainersIntegrationTest`: 4 JUnit tests, Confluent Kafka in Docker, `@ServiceConnection`.
- **Total: 7 JUnit tests.**

Each test uses a separate topic; producer and consumer use String serializer/deserializer. There are two partitions and one listener consumer assigned both partitions.

### 7.1. Gradle dependencies

Snippet from `build.gradle` already having the Spring Boot 3.5 plugin/BOM, repositories, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    // Artifact names in Boot 3.5 / Testcontainers 1.21.x:
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

### 7.2. Maven dependencies

Snippet in `pom.xml` with Spring Boot 3.5 parent/BOM and JUnit Platform runner:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>kafka</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

These are dependency snippets, not complete build files. Do not set arbitrary Kafka/Spring Kafka/Testcontainers versions when the Boot BOM already manages them. With Testcontainers 2.x you must update artifacts and verify the corresponding imports.

### 7.3. File tree

```text
src/
├── main/
│   ├── java/com/example/kafkalab/
│   │   ├── KafkaLabApplication.java
│   │   ├── KafkaTopicConfiguration.java
│   │   ├── OrderEventPublisher.java
│   │   └── OrderEventReceiver.java
│   └── resources/
│       └── application.properties
└── test/java/com/example/kafkalab/
    ├── EmbeddedKafkaIntegrationTest.java
    └── KafkaTestcontainersIntegrationTest.java
```

### 7.4. Application bootstrap

**File `src/main/java/com/example/kafkalab/KafkaLabApplication.java`:**

```java
package com.example.kafkalab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;

@SpringBootApplication
@EnableKafka
public class KafkaLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(KafkaLabApplication.class, args);
    }
}
```

`@EnableKafka` enables annotation-driven `@KafkaListener`. Spring Boot auto-configuration provides `KafkaTemplate`, `KafkaAdmin`, and listener infrastructure when the right dependencies and configurations are present.

### 7.5. Creating topics via KafkaAdmin/NewTopic

**File `src/main/java/com/example/kafkalab/KafkaTopicConfiguration.java`:**

```java
package com.example.kafkalab;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration(proxyBeanMethods = false)
public class KafkaTopicConfiguration {

    @Bean
    NewTopic orderEventsTopic(
            @Value("${app.kafka.topic}") String topic) {

        return TopicBuilder.name(topic)
                .partitions(2)
                .replicas(1)
                .build();
    }
}
```

A 2-partition topic allows testing partition-aware behavior. Replication factor 1 is a choice **only for a single-broker demo**. If `replicas=3` is configured on a single-node broker, topic creation fails; a production cluster needs appropriate `replicas`/`min.insync.replicas`.

Spring Boot's `KafkaAdmin` can create `NewTopic` beans when the context starts. In the Embedded Kafka test, the topic is also declared in `@EmbeddedKafka(topics=...)`; the two declarations must be consistent. In the Testcontainers class, `KafkaAdmin` creates the topic on the broker container.

### 7.6. Publisher using a real KafkaTemplate

**File `src/main/java/com/example/kafkalab/OrderEventPublisher.java`:**

```java
package com.example.kafkalab;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafka;
    private final String topic;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafka,
            @Value("${app.kafka.topic}") String topic) {
        this.kafka = kafka;
        this.topic = topic;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String key, String value) {
        validate(key, value);
        return kafka.send(topic, key, value);
    }

    public CompletableFuture<SendResult<String, String>>
            publishWithCorrelationId(
                    String key,
                    String value,
                    String correlationId) {

        validate(key, value);
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException(
                    "correlationId must not be blank");
        }

        ProducerRecord<String, String> record =
                new ProducerRecord<>(topic, key, value);
        record.headers().add(
                "x-correlation-id",
                correlationId.getBytes(StandardCharsets.UTF_8));
        return kafka.send(record);
    }

    private static void validate(String key, String value) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key is blank");
        }
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is blank");
        }
    }
}
```

The production service does not block on the future; **tests** can call `get(timeout)` to obtain the broker ACK and metadata. Do not assume `KafkaTemplate.send` succeeded just because the method returned a future; the future can complete exceptionally due to serializer, metadata, broker, or network errors.

### 7.7. Consumer with KafkaListener and test-observation queue

**File `src/main/java/com/example/kafkalab/OrderEventReceiver.java`:**

```java
package com.example.kafkalab;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventReceiver {

    public record Received(
            String key,
            String value,
            int partition,
            long offset,
            String correlationId) {}

    private final BlockingQueue<Received> queue =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            id = "orders-listener",
            topics = "${app.kafka.topic}",
            groupId = "${app.kafka.group}")
    public void onRecord(ConsumerRecord<String, String> record) {

        Header header = record.headers()
                .lastHeader("x-correlation-id");

        String correlationId = header == null
                ? null
                : new String(header.value(),
                        StandardCharsets.UTF_8);

        queue.offer(new Received(
                record.key(),
                record.value(),
                record.partition(),
                record.offset(),
                correlationId));
    }

    public Received await(Duration timeout)
            throws InterruptedException {
        return queue.poll(timeout.toMillis(),
                TimeUnit.MILLISECONDS);
    }

    public void clear() {
        queue.clear();
    }
}
```

`BlockingQueue` is solely a callback observation tool for the example. It is not a durable event store, does not commit consumer offsets, and does not create exactly-once business semantics. In real applications, listeners typically call a service/DB; to verify business processing, assert the DB or another observable output.

### 7.8. Kafka client configuration

**File `src/main/resources/application.properties`:**

```properties
# Default for manual local run; tests replace this endpoint.
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer

app.kafka.topic=orders.events.local
app.kafka.group=orders.local
spring.kafka.consumer.auto-offset-reset=latest
```

When running `main()` with this config, a real Kafka broker is needed at `localhost:9092`. In **Embedded Kafka tests**, the annotation remaps bootstrap to the embedded broker. In **Testcontainers tests**, `@ServiceConnection` prioritizes the container bootstrap. Never connect to production Kafka in CI.

## 8. Test mechanisms to prevent races and wrong offsets

Before looking at the two test classes, understand three points.

**First**, the Spring test context starting does not mean the consumer has joined the group or been assigned partitions. With a listener at `concurrency=1` and a 2-partition topic, use:

```java
MessageListenerContainer container =
        listenerRegistry.getListenerContainer("orders-listener");

ContainerTestUtils.waitForAssignment(container, 2);
```

This is a snippet inside a test context; it ensures partition assignment is complete before sending messages. If you change concurrency, partition count, or listener implementation, the wait condition must be adjusted.

**Second**, Kafka sends asynchronously. Use:

```java
SendResult<String, String> ack =
        publisher.publish("order-1", "CREATED")
                .get(10, TimeUnit.SECONDS);
```

This is the producer acknowledgment, not callback processing. To observe the listener:

```java
OrderEventReceiver.Received event =
        receiver.await(Duration.ofSeconds(10));

assertThat(event).isNotNull();
```

Do not use `Thread.sleep(300)` as a "guarantee".

**Third**, topic/group IDs must have isolation. Each test class uses its own topic, group, and keys. If a broker is shared across multiple JUnit workers, namespace by run ID rather than hardcoding demo names alone.

## 9. Testing with Embedded Kafka (3 JUnit methods)

**File `src/test/java/com/example/kafkalab/EmbeddedKafkaIntegrationTest.java`:**

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = KafkaLabApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "app.kafka.topic=orders.events.embedded",
        "app.kafka.group=orders.embedded.group",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.listener.concurrency=1",
        "spring.kafka.admin.fail-fast=true"
    }
)
@EmbeddedKafka(
    kraft = true,
    partitions = 2,
    topics = "orders.events.embedded",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class EmbeddedKafkaIntegrationTest {

    @Autowired OrderEventPublisher publisher;
    @Autowired OrderEventReceiver receiver;
    @Autowired KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 2);
        receiver.clear();
    }

    @Test
    void recordTravelsThroughEmbeddedBroker()
            throws Exception {
        SendResult<String, String> result =
                publisher.publish("E-01", "CREATED")
                        .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.key()).isEqualTo("E-01");
        assertThat(received.value()).isEqualTo("CREATED");
        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("orders.events.embedded");
        assertThat(received.partition()).isEqualTo(
                result.getRecordMetadata().partition());
        assertThat(received.offset()).isEqualTo(
                result.getRecordMetadata().offset());
    }

    @Test
    void unicodePayloadAndCorrelationHeaderSurvive()
            throws Exception {
        publisher.publishWithCorrelationId(
                "E-02", "Order created successfully",
                "trace-embedded-02")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.value()).isEqualTo(
                "Order created successfully");
        assertThat(received.correlationId()).isEqualTo(
                "trace-embedded-02");
    }

    @Test
    void sameKeyIsOrderedWithinOnePartition()
            throws Exception {
        publisher.publish("E-03", "CREATED")
                .get(10, TimeUnit.SECONDS);
        publisher.publish("E-03", "PAID")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received first =
                receiver.await(Duration.ofSeconds(10));
        OrderEventReceiver.Received second =
                receiver.await(Duration.ofSeconds(10));

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.value()).isEqualTo("CREATED");
        assertThat(second.value()).isEqualTo("PAID");
        assertThat(first.partition()).isEqualTo(
                second.partition());
        assertThat(first.offset()).isLessThan(
                second.offset());
    }
}
```

**These three tests use a real embedded broker.** The exact same production producer/consumer run; there is no Docker. `@DirtiesContext(AFTER_CLASS)` reduces the risk of the context cache keeping an embedded broker bean after its lifecycle ends, especially in multi-class test suites.

The first test compares producer metadata with the record received by the listener. The second test verifies UTF-8 and custom headers. The third test checks ordering within a single partition only. None of the tests claims DB transactions, offset commits, or retry/DLT were tested.

## 10. Testing with Kafka Testcontainers (4 JUnit methods)

**Prerequisites:** a running Docker daemon or compatible runtime with permission to pull `confluentinc/cp-kafka:7.8.0`. Without Docker, this test suite cannot run and CI must report that clearly rather than treating it as passing coverage.

**File `src/test/java/com/example/kafkalab/KafkaTestcontainersIntegrationTest.java`:**

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.ConfluentKafkaContainer;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.kafka.KafkaConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
    classes = KafkaLabApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "app.kafka.topic=orders.events.container",
        "app.kafka.group=orders.container.group",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.listener.concurrency=1",
        "spring.kafka.admin.fail-fast=true"
    }
)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class KafkaTestcontainersIntegrationTest {

    @Container
    @ServiceConnection
    static final ConfluentKafkaContainer KAFKA =
            new ConfluentKafkaContainer(
                    "confluentinc/cp-kafka:7.8.0");

    @Autowired KafkaConnectionDetails details;
    @Autowired OrderEventPublisher publisher;
    @Autowired OrderEventReceiver receiver;
    @Autowired KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 2);
        receiver.clear();
    }

    @Test
    void springBootUsesContainerBootstrapServers() {
        assertThat(KAFKA.isRunning()).isTrue();
        assertThat(details.getBootstrapServers())
                .contains(KAFKA.getBootstrapServers());
    }

    @Test
    void sendAndReceiveThroughContainerBroker()
            throws Exception {
        SendResult<String, String> result =
                publisher.publish("C-01", "CREATED")
                        .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.key()).isEqualTo("C-01");
        assertThat(received.value()).isEqualTo("CREATED");
        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("orders.events.container");
        assertThat(received.partition()).isEqualTo(
                result.getRecordMetadata().partition());
    }

    @Test
    void correlationHeaderSurvivesContainerTransport()
            throws Exception {
        publisher.publishWithCorrelationId(
                "C-02", "CONFIRMED",
                "trace-container-02")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.value()).isEqualTo("CONFIRMED");
        assertThat(received.correlationId()).isEqualTo(
                "trace-container-02");
    }

    @Test
    void sameKeyKeepsPartitionAndOffsetOrder()
            throws Exception {
        publisher.publish("C-03", "CREATED")
                .get(10, TimeUnit.SECONDS);
        publisher.publish("C-03", "PACKED")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received first =
                receiver.await(Duration.ofSeconds(10));
        OrderEventReceiver.Received second =
                receiver.await(Duration.ofSeconds(10));

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.value()).isEqualTo("CREATED");
        assertThat(second.value()).isEqualTo("PACKED");
        assertThat(first.partition()).isEqualTo(
                second.partition());
        assertThat(first.offset()).isLessThan(
                second.offset());
    }
}
```

The Testcontainers class keeps **the exact same production KafkaLabApplication, KafkaTopicConfiguration, OrderEventPublisher, and OrderEventReceiver**. Only the bootstrap broker, topic/group settings, and Docker image differ. `@EmbeddedKafka` is not needed in this class.

**Test 1** verifies that the container is running and Boot connection details point to the right broker. **Tests 2–4** run producer/consumer through the container broker, checking key/value, headers, and ordering. Hardcoded `localhost:9092` is not used as the final target because the service connection takes precedence with the container bootstrap.

### 10.1. Why not call @DynamicPropertySource together with @ServiceConnection?

Both can supply bootstrap configuration. In the example, **one** mechanism is used: Boot-managed `@ServiceConnection`. If a project does not use `spring-boot-testcontainers`, you can omit `@ServiceConnection` and add `@DynamicPropertySource` pointing to `KAFKA::getBootstrapServers`. Ensure no other property or custom bean overrides it with the wrong address.

### 10.2. Why not create a new container per test method?

A static `@Container` lets Testcontainers JUnit manage one container shared across the test class, reducing startup/image cost. Each test method still needs separate keys and clean receiver state. When tests run in parallel and share a Kafka broker, use explicit topic/group namespaces or stronger test isolation.

### 10.3. Why put @DirtiesContext on the container test class?

The Spring TestContext cache may retain beans configured with the container's bootstrap address after the JUnit extension stops the container. For a demo class, `@DirtiesContext(AFTER_CLASS)` closes the context alongside its lifecycle. In large suites, pick a consistent container/context sharing strategy; do not use a stopped broker from other cached contexts.

## 11. Running the example with Gradle/Maven

Linux/macOS:

```bash
# Embedded (no Docker required)
./gradlew test --tests "com.example.kafkalab.EmbeddedKafkaIntegrationTest"

# Testcontainers (Docker required)
./gradlew test --tests "com.example.kafkalab.KafkaTestcontainersIntegrationTest"

# If the project uses Maven:
./mvnw -Dtest=EmbeddedKafkaIntegrationTest test
./mvnw -Dtest=KafkaTestcontainersIntegrationTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.kafkalab.EmbeddedKafkaIntegrationTest"
.\gradlew.bat test --tests "com.example.kafkalab.KafkaTestcontainersIntegrationTest"

# Or Maven Wrapper:
.\mvnw.cmd "-Dtest=EmbeddedKafkaIntegrationTest" test
.\mvnw.cmd "-Dtest=KafkaTestcontainersIntegrationTest" test
```

Use the project's actual build tool; both are not required. With Docker Testcontainers, allow image pulls, socket/daemon access, port mapping, and appropriate CPU/RAM. A run skipped due to missing Docker **must not be reported as having tested the broker container**.

### 11.1. Expected test report

| Class | `@Test` method count | Broker | Docker? |
|---|---:|---|---|
| `EmbeddedKafkaIntegrationTest` | 3 | Embedded KRaft broker | No |
| `KafkaTestcontainersIntegrationTest` | 4 | Confluent cp-kafka container | Yes |
| **Total** | **7** | Two independent test environments | Per class |

**Expected goal:** 7 JUnit tests pass in a compatible environment. This is sample code checked against documentation/APIs, **not results compiled or executed during authoring**. There is no fixed application stdout; broker, JUnit, and Maven/Gradle logs vary in timing and ordering.

## 12. Common causes of flaky Kafka tests

### 12.1. Sending before the consumer is assigned

A started context does not mean the listener has been assigned Kafka partitions. If you send too early and the group starts at `latest`, the consumer may miss the message. Use `ContainerTestUtils.waitForAssignment(...)` before publishing or an equivalent synchronization mechanism.

### 12.2. Reusing the same topic/group across tests

Topics retain records and groups keep committed offsets. Running a single test alone versus running the full suite can yield different results. With a shared broker:

- Create separate topics/groups per class/run.
- Never use production groups.
- Choose `earliest`/`latest` intentionally.
- When replay is needed, use a new group or seek; switching to `earliest` alone is not enough when committed offsets already exist.
- Do not unintentionally share a group between a probe consumer and the application listener.

In the sample, each class uses its own topic/group and each test method uses distinct keys; clearing the queue in `@BeforeEach` prevents retaining observations from prior tests.

### 12.3. Waiting with a fixed sleep

`Thread.sleep(200)` might suffice on a developer laptop yet fail in CI. Milestones to wait for separately:

1. `KafkaAdmin` creates the topic and the broker is ready.
2. Consumer joins / gets partition assignment.
3. Producer receives ACK.
4. Listener callback runs.
5. Business side effect completes (if any).

Use appropriate bounded waits/probes rather than a single fixed sleep.

### 12.4. Fake ordering

Two keys can be routed to two partitions. Do not assert global order across all records. For per-order/per-account ordering, design a stable partition key. Producer retries/idempotence/concurrency and versions also matter if testing ordering under failure.

### 12.5. Consumer lag and offset commit

The listener successfully receiving a record does not prove the offset was committed per ack mode. If you need to test restart/resume/offset correctness, you must stop/restart the consumer container, check group/offsets, and observe replay. The sample only tests callback receipt, not Kafka offset transactions.

## 13. Error handling, retries, and Dead Letter Topics

A happy-path test like the example **does not yet test**:

- JSON/Avro deserialization failures.
- Business exceptions thrown by the listener.
- Producer broker timeouts.
- Kafka consumer retry/backoff.
- `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, or `@RetryableTopic`.
- DLT topic destination/partition/headers.
- Poison pills blocking partition progress.
- Consumer offset commits after recovery.

### 13.1. DLT tests require a real broker path

If DLT integration is needed:

1. Create the source topic and DLT topic with matching partitions.
2. Configure the test error handler/recoverer and retry policy.
3. Send a real poison pill that makes the listener throw.
4. Wait for the expected attempts/handler path.
5. Use a separate consumer group to read the DLT.
6. Assert key, value/raw bytes, error headers, partition, and destination topic.
7. Ensure timeouts and retry counts are bounded.

Mocking `DeadLetterPublishingRecoverer.accept(...)` only proves the method was called, **not** that the DLT record was stored by the broker.

### 13.2. Illustrative policy example

```java
@Bean
DefaultErrorHandler errorHandler(
        KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);
    return new DefaultErrorHandler(
            recoverer, new FixedBackOff(0L, 2L));
}
```

This is a **snippet**, not a runnable file in the 7-test example. It needs imports, serializers/deserializers, and proper DLT provisioning. With `FixedBackOff(0L, 2L)`, verify the retry attempt semantics of the handler version in use. Do not use default production configs without reviewing retryable exceptions, poison-pill behavior, and throughput.

### 13.3. When to choose Embedded vs. Container for DLT?

If you only check policy/error handler behavior and DLT publish/consume, Embedded Kafka may suffice. If the test depends on broker/image version, security, networking, or broker-specific config, use Testcontainers. With Schema Registry/Avro/Protobuf, consider a separate schema registry container or appropriate contract/schema tests.

## 14. Transactions and exactly-once: do not over-claim from send/receive

### 14.1. Kafka producer transactions

Kafka supports transactions and idempotent producers. A producer can ACK a record before a transaction commits. If the transaction aborts, a consumer using `isolation.level=read_committed` does not see the aborted record. Thus:

- Send future completion does not equal Kafka transaction commit.
- Listener receive does not prove a DB commit.
- Consumer acknowledgment/offset commit does not mean an exactly-once business operation in external systems.

A Kafka transaction test should create a transactional producer, explicitly commit/abort, use a `read_committed` consumer, and assert committed/aborted records.

### 14.2. DB and Kafka are two resource boundaries

A service using `@Transactional` with JPA to write to a DB and then calling `KafkaTemplate.send` does not automatically get a distributed XA transaction across both resources. The process can crash after DB commit and before Kafka publish, or the Kafka event can commit while an HTTP call fails.

Ways to improve safety:

- Transactional outbox/inbox.
- Idempotent event consumers keyed by event ID.
- Unique constraints/deduplication.
- Recovery/retry and dead-letter policies.
- Testing controlled failure points between commits.
- Measuring processing effects outside Kafka, not just queue callbacks.

Embedded Kafka/Testcontainers help verify the real Kafka path, but **cannot replace** a consistency architecture between database and Kafka.

## 15. Security, compatibility, Docker networking, and HA

### 15.1. Single broker is not an HA cluster

Both the embedded KRaft broker and the Confluent container in this lesson are a single broker with `replicas=1`. They do not test:

- Replication factor 3, `min.insync.replicas`, or ISR shrink.
- Leader election or controller quorum failover.
- Broker crash/restart mid-produce/consume.
- Rack awareness and partition reassignment.
- Rolling upgrades.
- Network partitions and backpressure under load.
- Multi-node throughput and durability targets.

If production SLAs depend on these properties, design a separate multi-node Kafka cluster/fault suite.

### 15.2. Advertised listeners

Kafka clients use the bootstrap address to fetch metadata containing broker endpoints. In Docker:

- The host JVM uses `KAFKA.getBootstrapServers()`.
- Another container cannot by default reach the host's `localhost:<mapped-port>`, because `localhost` inside a container points to that container itself.
- If the app runs inside another container, you may need to register an additional listener suited to the Docker network.
- Wrong advertised listeners let initial bootstrap connect while subsequent send/poll calls time out.

Never hardcode `localhost:9092` for Kafka Testcontainers. With Spring Boot auto-config, `@ServiceConnection` avoids most host-side mapped port mistakes.

### 15.3. TLS/SASL/ACL

Local demo brokers typically use PLAINTEXT. They do not test certificate chains, mTLS, SASL/PLAIN/SCRAM, OAuthBearer, topic/group/transactional ID ACLs, production DNS/proxies, or secret rotation. If these are key risks, use a test broker with matching security config or a permitted staging environment.

Never put production credentials, PII, or SASL secrets into source or test logs. Kafka record values/headers may hold sensitive data; broker/test runner logs require redaction.

### 15.4. Version matrix

A Kafka protocol client can interoperate with multiple broker versions, though not all combinations support the exact same features. Pin and document:

- Spring Boot version.
- Spring Kafka/kafka-clients version managed by the BOM.
- Testcontainers major/module version.
- Kafka image and broker version.
- Serializer/schema versions.
- Security/protocol configuration.

Only bump Kafka image tags with compatibility tests; do not assume embedded tests using classpath-bundled brokers replace Testcontainers image tests.

## 16. Debugging common errors

| Symptom | Common cause | Solution |
|---|---|---|
| Test connects to localhost:9092 | Test bootstrap override not applied | `@EmbeddedKafka` `bootstrapServersProperty` or `@ServiceConnection` |
| `@EmbeddedKafka` yet client waits for external broker | Custom `ProducerFactory` ignores Spring properties | Use Boot auto-config or pass test broker address to custom factory |
| Consumer receives no records | Not assigned yet, wrong topic/group, offset latest | Wait for assignment, use fresh group/`earliest` |
| Consumer receives old events | Shared topic/group and retained messages | Isolate topic/group, clear probe queue |
| Test send future hangs | `KafkaAdmin`/topic/metadata/broker network error | Bounded future timeout, inspect logs/topic |
| `KafkaListener` does not run | Missing `@EnableKafka`/bean scan/topic/deserializer | Check listener registry, group, and logs |
| No class `ConfluentKafkaContainer` | Wrong Testcontainers artifact/version | Boot 3.5 uses `org.testcontainers:kafka` and matching package |
| Docker environment unavailable | Daemon not running/insufficient CI permissions | Use Docker job, Testcontainers Cloud, or split suite |
| Image pull failed | Registry/proxy/quota policy | Pin/mirror image, prepare CI registry access |
| Container runs yet Kafka times out | Wrong advertised listener | `getBootstrapServers`/`ServiceConnection`, proper networking |
| Topic creation fails | `KafkaAdmin` missing/`replicas>brokers` | `NewTopic` `partitions=2, replicas=1` |
| `KafkaTemplate` sends String with wrong serializer | Key/value serializer mismatch | Matching `StringSerializer` and `StringDeserializer` |
| Key/value differs from expectation | Different charset/headers/serialization | Verify record metadata + listener payload |
| Cross-partition ordering test fails | Kafka only orders per partition | Same key/partition; assert offsets |
| No records in DLT | Missing error handler/partition/topic | Configure recoverer + consume DLT with separate group |
| Committed group does not replay | `earliest` does not apply when offsets exist | Fresh group or explicit seek |
| Testcontainers test skipped | CI lacks Docker or test filter only runs Embedded | Check JUnit skipped count and Docker job |
| Embedded shutdown race | Context cache vs. broker bean lifecycle | `@DirtiesContext` or lifecycle strategy |
| Retries cause duplicate business actions | At-least-once delivery | Idempotent consumer + domain deduplication |
| Tests pass yet production TLS fails | Tests used PLAINTEXT | Separate security integration suite |
| Spring Boot 4 imports fail | Different major starter/test module packages | Follow version-specific docs |

### 16.1. Effective diagnostic sequence

1. Identify whether the test uses Embedded Kafka or Testcontainers; do not mix bootstraps unintentionally.
2. Check the dependency tree against Spring Boot 3.5/Spring Kafka 3.3/Testcontainers 1.21.
3. Inspect broker startup/logs and topic provisioning.
4. Check the bootstrap source: embedded system property or container connection details.
5. Check topic, group ID, and listener container ID.
6. Wait for consumer assignment; verify partition count.
7. Check producer serializer, consumer deserializer, and record metadata.
8. Await `KafkaTemplate` future and then listener callback with bounded timeouts.
9. If containerized: check Docker runtime, mapped ports, advertised listeners, image.
10. If the test requires retry/DLT/transactions/HA: check whether dedicated configs and assertions exist.

## 17. Practice questions with answers

### Question A. Why does Mockito not prove Kafka integration?

A unit test verifies `kafkaTemplate.send(topic, key, event)` was called once. A developer changes the serializer to the wrong type. The test stays green. Why?

**Answer:** the mock only verifies a Java method invocation. Embedded Kafka/Testcontainers run the real serializer, broker, and listener, catching wiring/type mismatches. Unit tests remain useful for business logic, but are insufficient for protocol integration.

### Question B. `@EmbeddedKafka` still connects to localhost:9092

**Answer:** check `bootstrapServersProperty="spring.kafka.bootstrap-servers"` or the broker property mapping; check whether custom factories ignore Boot properties. Never fix this by pointing tests at a production address.

### Question C. Does Testcontainers have a fixed Kafka bootstrap port?

**No.** Use `@ServiceConnection`/`KafkaConnectionDetails` or `KAFKA.getBootstrapServers()`. Docker maps ports dynamically; never assume `localhost:9092`.

### Question D. When is a producer ACK not enough?

Producer future succeeds, yet the consumer receives nothing. **Answer:** ACK reflects broker send, not consumer assignment/processing. Check topic, group, offsets, listener registration, and deserializer; await the callback separately.

### Question E. Record ordering across two partitions

Two records have different keys; B is received before A. Is Kafka broken?

**No.** Kafka only guarantees ordering per partition. If the domain needs per-entity order, use a stable key and assert the same partition/offset.

### Question F. `earliest` does not replay

Changed `auto-offset-reset=earliest` yet the group still does not read old records. **Answer:** the group has valid committed offsets; create a fresh group or perform an explicit seek.

### Question G. Testing a Dead Letter Topic

Mocking the error handler passes, yet the DLT receives no events. **Answer:** unit mocks do not test broker publishing. Send a real poison pill, configure recoverer/source/DLT, and read the DLT using a separate consumer group.

### Question H. Does Kafka Testcontainers match production HA?

**No.** A single-node container does not test multi-broker replication, ISR, leader failover, or TLS/SASL unless configured. Dedicated cluster tests are required.

### Question I. Kafka record ACKed but transaction aborted

With a `read_committed` consumer, is the record visible? **Normally no**, because aborted transactions are not exposed to `read_committed` consumers.

### Question J. Kafka and JPA sharing `@Transactional`

Does it guarantee atomic commit across DB and Kafka? **Not by default.** They are separate resource transactions. Consider outbox, idempotency, and recovery.

### Question K. CI without Docker

Embedded Kafka tests pass while Testcontainers tests do not run. Can you report all integration tests PASSED? **No.** Report only coverage that actually executed, configure a Docker-capable job, or explicitly report skipped counts.

## 18. Kafka integration test completion checklist

- [ ] Chose the right level: unit, Embedded Kafka, Testcontainers, or real cluster.
- [ ] Do not mock `KafkaTemplate` in tests called broker integration.
- [ ] Real Kafka producer/consumer configuration and matching serializers/deserializers.
- [ ] Spring Boot/Spring Kafka/Testcontainers/BOM versions pinned.
- [ ] Embedded Kafka uses the right KRaft/bootstrap options for the version branch.
- [ ] Kafka container uses the right class, artifact, and Docker image.
- [ ] Boot `KafkaConnectionDetails` points to the container, not a production broker.
- [ ] Topic actually created with appropriate partitions/replicas.
- [ ] Listener assigned before the test publishes.
- [ ] No `Thread.sleep` used as a pass condition.
- [ ] Tests await `KafkaTemplate` future and listener callback separately.
- [ ] Assertions cover record key/value, metadata, and headers.
- [ ] No global ordering asserted across partitions.
- [ ] Group ID/topic isolated, offset reset handled properly.
- [ ] Probe consumer does not accidentally share a group with the application.
- [ ] DLT/retry/transactions claimed as tested only when real configs/scenarios exist.
- [ ] Broker ACK not confused with consumer DB state/offset commit.
- [ ] Kafka transactions not confused with distributed DB+Kafka XA.
- [ ] Docker/Testcontainers availability checked and skip/fail reported clearly.
- [ ] Image/Kafka protocol versions compatibility-tested.
- [ ] Advertised listeners/host-container networking configured properly.
- [ ] TLS/SASL/ACL tested separately if in scope.
- [ ] Single-node container not labeled a multi-node availability test.
- [ ] Embedded broker lifecycle/context cache managed.
- [ ] Tests run independently, order-free, with no message leakage.
- [ ] Logs redacted, containing no production credentials/PII.
- [ ] JUnit report records executed/passed/failed/skipped counts.
- [ ] Test results do not claim unconfigured features.

## 19. Conclusion

**Embedded Kafka** and **Kafka in Testcontainers** both enable real Kafka broker integration testing, differing in runtime environment and closeness to deployment. Embedded requires no Docker and works well for frequent integration suites; Testcontainers uses a specific Kafka image/version, fitting containerized broker compatibility and multi-service setups.

A good test does more than start a broker. It verifies **the producer can send**, **the listener is ready**, **the consumer actually receives**, **messages/metadata are right**, and **test state is isolated**. For retries, DLT, transactions, security, or high availability, add dedicated suites with real configuration to avoid false confidence.

The example uses the same production source across both test environments with **7 JUnit methods** (3 embedded, 4 container). Outcomes are described as expectations per the APIs/versions; they must be compiled and run in an appropriate environment before serving as empirical proof for a specific application.

## Official References

- [Spring Kafka 3.3 — Testing Applications](https://docs.spring.io/spring-kafka/reference/3.3/testing.html): `EmbeddedKafkaBroker`, KRaft, `@EmbeddedKafka`, `KafkaTestUtils`, listener/offset notes, and test lifecycle.
- [Spring Kafka 3.3 — EmbeddedKafka annotation API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/test/context/EmbeddedKafka.html): broker options, topics, partitions, bootstrap property.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, `KafkaConnectionDetails`, connection precedence.
- [Spring Boot 3.5 — Managed dependency coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Spring Kafka 3.3.x, Testcontainers 1.21.x modules.
- [Spring Boot 3.5 — Kafka messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/kafka.html): `KafkaTemplate`, `KafkaAdmin`, `NewTopic`, Kafka listeners.
- [Testcontainers Java — Kafka Module](https://java.testcontainers.org/modules/kafka/): `ConfluentKafkaContainer`, `KafkaContainer`, image versions, bootstrap servers, and additional listeners.
- [Spring Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` async results.
- [Spring Kafka — Error Handling](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, DLT/recoverer.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transactions and consumer offset coordination.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): topics, partitions, consumer groups, offsets, producer transactions, durability.
