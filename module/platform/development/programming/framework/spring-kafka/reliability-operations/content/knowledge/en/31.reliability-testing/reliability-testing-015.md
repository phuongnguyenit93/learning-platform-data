# Embedded Kafka and Testcontainers — Reliability Testing in Spring Kafka

## 1. Why do Kafka systems need integration tests with a real broker?

A Spring Kafka application can pass every unit test and still fail in production:

- The producer serializes objects properly in unit tests, yet the broker rejects messages because the topic does not exist or ACLs are wrong.
- The consumer handles business logic properly, yet `@KafkaListener` never receives records due to a wrong `group.id`, topic, or deserializer.
- Retries are configured, yet a poison message traps a partition in an infinite processing loop.
- Records routed to the dead-letter topic (DLT) land on the wrong partition or lack headers needed for tracing.
- The consumer finishes processing data without committing the offset; after a crash, records get redelivered.
- Tests pass locally on a developer laptop yet fail randomly on CI because the listener had not been assigned partitions yet.
- A newer Kafka broker, Kafka client, or Spring Kafka version alters behavior in ways mocks cannot simulate.

**Embedded Kafka** and **Testcontainers** test real send/receive flows instead of merely mocking `KafkaTemplate` or calling listener methods directly.

The two tools address different goals:

- **Embedded Kafka** starts a test Kafka broker inside the test JVM environment; fast to configure and integrates smoothly with `spring-kafka-test`.
- **Testcontainers** runs a Kafka broker inside a Docker container; provides stronger process/OS isolation and pairs easily with PostgreSQL, Redis, schema registries, or network proxies to test multi-component interactions.

In the **Spring Kafka Reliability Operations** module, choosing a test environment must start with one question: **which reliability risk needs to be proven?** Testing receipt of one record differs from proving retries do not lose data, and both differ from testing real broker failover.

This article uses **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, JUnit 5, and Testcontainers 1.x** as the baseline. Kafka/Spring Kafka/Testcontainers versions evolve continuously; align dependency versions with your project BOM. For Spring Boot 4/Spring Kafka 4/Testcontainers 2, check packages and APIs before copying examples verbatim.

### Learning objectives

After this lesson, you will be able to:

1. Choose between Embedded Kafka and Testcontainers based on goals, limitations, and test cost.
2. Configure `spring-kafka-test`, `@EmbeddedKafka`, `@SpringBootTest`, and bootstrap servers.
3. Send records with `KafkaTemplate`, receive them with a real Kafka consumer, and assert results.
4. Test asynchronous `@KafkaListener`s without relying on `Thread.sleep`.
5. Spin up an isolated Kafka container with `@Testcontainers` and `@DynamicPropertySource`.
6. Write tests for retries, DLTs, offsets, replay, ordering, and idempotent processing.
7. Identify where fault injection or a multi-broker Kafka cluster is required.
8. Organize isolated, repeatable tests suited for CI and production operations.

---

## 2. Layering tests before choosing tools

Do not start Kafka for every test. A reliable test suite divides work by what must be verified.

| Test tier | Components | What it verifies | What it does not fully cover |
| --- | --- | --- | --- |
| Unit test | Mockito/fakes, domain services | Validation, mapping, business decisions | Real serialization, broker, groups/offsets |
| Lightweight slice/integration | Spring context + Embedded Kafka | Producer/consumer wiring, topics, partitions, serialization, listeners | Docker networking, OS process isolation, cluster failover |
| Container integration | Spring + Kafka Testcontainers | Kafka broker in a separate process, network endpoints, combined DB/containers | Production broker topology, security, and multi-zone unless configured |
| Multi-container reliability | Kafka + DB + proxy/chaos + workers | Network partitions, recovery, cross-service idempotency | Every characteristic of a production cluster |
| Preproduction / staging | Production-like broker cluster | ACLs/TLS, replication, ISR, rebalancing, throughput | Cannot prove every possible future incident absolutely |

Effective rule: use **unit tests for pure logic**, **Embedded Kafka for fast feedback loops**, **Testcontainers for high-confidence integration with real technology**, and **cluster tests** for distributed/high-availability scenarios.

### 2.1. Testing "record received" is a first step, not enough

A test like:

```text
producer.send() -> broker -> consumer.poll() -> assert value
```

proves a record can travel under normal conditions. It **does not automatically prove**:

- Does the consumer behave properly when the listener throws an exception?
- Does offset commit happen before or after DB commit?
- Can records be reprocessed safely after a crash?
- Is there a DLT when retries are exhausted?
- Does the producer preserve ordering across partitions?
- Does a single-node broker survive a node failure?
- Are TLS/SASL settings compatible with production?

We will build these scenarios separately, avoiding treating a "happy path" test as proof of exactly-once.

---

## 3. Embedded Kafka vs. Testcontainers: practical comparison

| Criterion | Embedded Kafka | Kafka Testcontainers |
| --- | --- | --- |
| Where broker runs | Inside test/JVM process via EmbeddedKafkaBroker | Separate Docker container |
| Startup | Usually fast for small tests | Image pull/container startup overhead |
| Docker required | No | Yes |
| Developer laptop/CI fit | Yes, Docker-free | Needs Docker runtime/daemon and images |
| Test configuration | `@EmbeddedKafka`, `spring-kafka-test` | `@Container` + dynamic bootstrap |
| Real Kafka behavior | Real Kafka broker for tests | Real Kafka broker in a container |
| Process isolation | Lower than containers | Clearer |
| Testing Kafka + PostgreSQL | Possible with other DBs, not the main focus | Convenient on the same Docker network |
| Network cuts between services | Hard to simulate realistically | Can add Toxiproxy/network controls |
| Multi-broker replication tests | Not default; needs custom topology | Not default; one container is usually one broker |
| CI speed/cost | Suits frequent runs | Typically reserved for selective integration suites |
| Production TLS/SASL | Needs specialized config | Can build topologies closer to production |
| Topic/group isolation | Still must be designed explicitly | Still must be designed explicitly |

**Commonality:** both can run a real Kafka broker for tests, yet typically run **only one broker**. One broker is enough to test message flow, not to prove fault tolerance of a cluster with replication factor 3 and `min.insync.replicas=2`.

### 3.1. When to prefer Embedded Kafka?

- Testing `KafkaTemplate` serialization and publishing.
- Testing `@KafkaListener` consumption and deserialization.
- Testing listener retries/DLTs at the integration level.
- Testing partition routing and keys on a single broker.
- CI environments with restricted Docker access.
- Needing many fast, independent application-level tests.

### 3.2. When to prefer Testcontainers?

- Testing a Spring Boot application with Kafka config matching deployment.
- Combining Kafka, PostgreSQL, Redis, service A, and service B.
- Testing idempotency/transactions when DB and Kafka run concurrently.
- Needing network manipulation via proxies, container pauses, or Docker routing.
- Verifying client compatibility with a specific Kafka image.
- Wanting consistent integration infrastructure across developer laptops and CI.

It is not true that "Testcontainers is always better." If the goal is simply testing a message mapper, both tools may be overkill.

---

## 4. Sample Spring Boot project

This practice builds a small application:

```text
Producer API / service
       |
       v
  KafkaTemplate<String, String>
       |
       v
  Topic: orders.created
       |
       v
  @KafkaListener
       |
       v
  Order handler / database projection

Tests:
  - EmbeddedKafka: send -> Kafka record
  - EmbeddedKafka: send -> @KafkaListener -> assertion
  - Testcontainers: send -> isolated Kafka broker -> record
  - Reliability: poison message -> retry -> DLT
  - Reliability: duplicate replay -> idempotent handler
```

### 4.1. Directory layout

```text
kafka-reliability-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/kafkalab/
    │   │   ├── KafkaLabApplication.java
    │   │   └── OrderPublisher.java
    │   └── resources/application.yml
    └── test/
        ├── java/com/example/kafkalab/
        │   ├── EmbeddedKafkaIntegrationTest.java
        │   ├── ListenerIntegrationTest.java
        │   ├── KafkaContainerIntegrationTest.java
        │   └── OrderIdempotencyTest.java
        └── resources/application-test.yml
```

### 4.2. Gradle dependencies

Example using Spring Boot 3.3.x / Spring Kafka 3.x and Testcontainers 1.x compatible with the Spring Boot BOM.

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'

    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'

    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot BOM manages common dependency versions; when using another Spring Boot version, verify compatibility across Kafka client, Testcontainers, and broker images. Some newer Testcontainers releases reorganize modules/packages; examples here intentionally use Testcontainers 1.x APIs for illustration.

`settings.gradle`:

```groovy
rootProject.name = 'kafka-reliability-lab'
```

### 4.3. Application and producer

`KafkaLabApplication.java`:

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

`OrderPublisher.java`:

```java
package com.example.kafkalab;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String topic,
            String orderId,
            String payload) {

        return template.send(topic, orderId, payload);
    }
}
```

Spring Kafka 3.x's `KafkaTemplate.send(...)` returns `CompletableFuture`. In production, producers normally should not block synchronously on every message; calling `future.get(...)` in integration tests simply confirms the broker accepted the record per producer configuration and applies a timeout so tests never hang forever.

### 4.4. Serializer/deserializer configuration

`src/test/resources/application-test.yml`:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
    listener:
      ack-mode: record
```

`bootstrap-servers` **must not be hard-coded** in this test file; Embedded Kafka or Testcontainers supplies the environment-specific endpoint.

Meaning:

- `acks=all`: broker awaits acknowledgements per ISR policy; on a single-broker cluster this is not proof of replication.
- `auto-offset-reset=earliest`: applies when a group has no committed offset yet; keeps fresh test consumers from missing records sent before subscribing.
- `enable-auto-commit=false`: lets the Spring listener container manage offsets instead of client auto-commit.
- `ack-mode=record`: the listener container typically commits offsets after the record listener succeeds per configured semantics. With retries/error handlers/transactions, commit behavior must be verified in specific scenarios.

The test configuration is activated via `@ActiveProfiles("test")`.

---

## 5. Embedded Kafka: an in-test broker

### 5.1. How does `@EmbeddedKafka` work?

`spring-kafka-test` provides:

- `@EmbeddedKafka` to request starting a Kafka broker for the test.
- `EmbeddedKafkaBroker` to access bootstrap servers, topics, and test utilities.
- `KafkaTestUtils` to build consumer/producer configs and read test records.
- `ContainerTestUtils` to help wait for listener container partition assignments.

When using a Spring context, Spring Kafka registers the test broker automatically. Avoid enabling different embedded broker startup styles simultaneously in the same suite unless intentional.

### 5.2. Testing publish → consume with a real Kafka client

`EmbeddedKafkaIntegrationTest.java`:

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = KafkaLabApplication.class)
@ActiveProfiles("test")
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.embedded.it"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class EmbeddedKafkaIntegrationTest {

    private static final String TOPIC = "orders.embedded.it";

    @Autowired
    OrderPublisher publisher;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void producerPublishesRecordToEmbeddedBroker()
            throws Exception {

        String groupId =
            "probe-" + UUID.randomUUID();

        Map<String, Object> consumerProps =
            KafkaTestUtils.consumerProps(
                groupId, "false", embeddedKafka);

        try (Consumer<String, String> consumer =
                new DefaultKafkaConsumerFactory<>(
                    consumerProps,
                    new StringDeserializer(),
                    new StringDeserializer()
                ).createConsumer()) {

            // Assign topic/partition and seek to start.
            // Prefer subscribing/assigning before publishing.
            embeddedKafka.consumeFromAnEmbeddedTopic(
                consumer, TOPIC);

            var result = publisher.publish(
                TOPIC, "order-42", "CREATED")
                .get(10, TimeUnit.SECONDS);

            assertEquals(TOPIC,
                result.getRecordMetadata().topic());

            var received = KafkaTestUtils.getSingleRecord(
                consumer, TOPIC, Duration.ofSeconds(10));

            assertEquals("order-42", received.key());
            assertEquals("CREATED", received.value());
            assertEquals(TOPIC, received.topic());
            assertEquals(0, received.partition());
        }
    }
}
```

### 5.3. Why use a dedicated consumer?

The test generates a random `group.id` so it never reads committed offsets from prior tests. The test consumer is closed via `try-with-resources` to release network connections.

`embeddedKafka.consumeFromAnEmbeddedTopic(...)` assigns partitions and seeks using Spring Kafka Test's utility, avoiding timing races around joining the group before publishing. When a topic has multiple partitions, inspect assignments and offsets per partition; never assume every key lands on partition 0.

### 5.4. `bootstrapServersProperty` matters

The annotation:

```java
@EmbeddedKafka(
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

publishes the embedded broker's bootstrap address into the property read by Spring Boot Kafka auto-configuration. Without setting the right property, `KafkaTemplate` may attempt to connect to `localhost:9092`, failing the test or accidentally hitting a Kafka broker running on the developer's machine.

In some `spring-kafka-test` versions, a default mapping to `spring.kafka.bootstrap-servers` may already exist; configuring it explicitly keeps the exercise readable and reduces dependence on version defaults.

### 5.5. Tests must prove both sides

A successful `future.get(...)` proves only that the message was sent per ack semantics. `KafkaTestUtils.getSingleRecord(...)` proves the test consumer received that record. To verify an application listener and business side effects, test that in the next step; never treat a raw consumer read as proof that the application's `@KafkaListener` works properly.

---

## 6. Testing asynchronous `@KafkaListener`s

### 6.1. Why do listener tests easily become flaky?

`@KafkaListener` executes on a container thread, not the JUnit thread. When a test sends a message and immediately asserts:

```java
publisher.publish(TOPIC, key, value);
assertEquals(1, processed.size()); // Flaky
```

the listener may not have been assigned partitions yet or may not have polled yet, even if the message is already in the broker.

Do not fix this with `Thread.sleep(5000)`:

- On a fast machine, the test wastes time.
- On slow CI, 5 seconds can still be too short.
- The test is not waiting on the actual condition that needs to occur.
- On failure, it is hard to tell a Kafka bug apart from a test race.

### 6.2. Creating a test-only probe listener

`ListenerIntegrationTest.java`:

```java
package com.example.kafkalab;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = KafkaLabApplication.class)
@ActiveProfiles("test")
@Import(ListenerIntegrationTest.ProbeConfig.class)
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.listener.it"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class ListenerIntegrationTest {

    @Autowired
    OrderPublisher publisher;

    @Autowired
    ProbeListener probe;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void listenerReceivesPublishedOrder() throws Exception {
        MessageListenerContainer container =
            registry.getListenerContainer(
                "orders-it-listener");

        assertNotNull(container);

        // Wait for the listener to be assigned a real partition.
        ContainerTestUtils.waitForAssignment(
            container, 1);

        publisher.publish(
            "orders.listener.it", "order-51", "APPROVED")
            .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> record =
            probe.received.poll(
                10, TimeUnit.SECONDS);

        assertNotNull(record);
        assertEquals("order-51", record.key());
        assertEquals("APPROVED", record.value());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ProbeConfig {

        @Bean
        ProbeListener probeListener() {
            return new ProbeListener();
        }
    }

    static class ProbeListener {

        private final BlockingQueue<ConsumerRecord<String, String>>
            received = new LinkedBlockingQueue<>();

        @KafkaListener(
            id = "orders-it-listener",
            topics = "orders.listener.it",
            groupId = "orders-listener-it"
        )
        public void onRecord(ConsumerRecord<String, String> record) {
            received.add(record);
        }
    }
}
```

The test uses `ContainerTestUtils.waitForAssignment(...)` as a readiness barrier for the listener, then waits via `BlockingQueue.poll(timeout)`. The test exits early as soon as the condition holds, and enforces a time limit if the event never arrives.

In real projects, inject the **business handler** and assert state persisted in the repository/database (externally observable output) rather than only inspecting a test queue. The queue here merely demonstrates the asynchronous testing mechanism.

### 6.3. What if the listener has multiple partitions?

Suppose `@EmbeddedKafka(partitions=3)` with listener concurrency=2. When calling `waitForAssignment`, the count passed must match the container's expected total assignments, not blindly `1`. If group rebalancing occurs, assignments can shift; tests should wait for a stable state before sending.

### 6.4. Using Awaitility for asynchronous results

When the handler writes to a repository:

```java
await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        assertTrue(repository.existsByEventId("evt-2001"));
    });
```

Matching import:

```java
import static org.awaitility.Awaitility.await;
```

This verifies **persisted business effects**. Never write `await().until(() -> true)` or simply wait for time to pass and assume Kafka finished.

---

## 7. Defining topics explicitly and isolating test data

### 7.1. Do not rely on unintended auto-created topics

A single-broker test may work even without declaring topics because Kafka auto-creates topics on producer send. This easily masks production bugs where `auto.create.topics.enable=false` or producers lack topic-creation permissions.

With Embedded Kafka:

```java
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders.input.it", "orders.input.it.DLT"},
    brokerProperties = {
        "auto.create.topics.enable=false"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

With Testcontainers and Spring Boot, declare `NewTopic` beans so `KafkaAdmin` creates topics at application startup:

```java
@Bean
NewTopic ordersTopic() {
    return TopicBuilder.name("orders.container.it")
        .partitions(1)
        .replicas(1)
        .build();
}
```

Imports:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.config.TopicBuilder;
```

In production, topic creation is typically managed by Terraform/Ansible/platform teams; `KafkaAdmin` in tests merely illustrates deterministic resource provisioning.

### 7.2. Remember both topics and consumer groups

To prevent tests from interfering with each other:

- Use dedicated test topic names per class/scenario.
- Use dedicated consumer group IDs or a fresh broker.
- If using a DLT, create the DLT topic explicitly.
- Never share `group.id` with production listeners or other tests.
- Reset/close consumers, listeners, and databases between tests when needed.
- When tests share a Spring context, use `@DirtiesContext` selectively; avoid applying it everywhere and slowing down the suite.

### 7.3. Offset reset config does not replace isolation

`auto.offset.reset=earliest` only takes effect **when a group has no valid committed offset**. Once a group has committed the end offset, a new consumer with the same group typically resumes from that committed offset rather than rewinding to the start.

Therefore, a test reading all records from the beginning must use a fresh group, assign/seek offsets explicitly, or start with a fresh broker/topic per fixture.

---

## 8. Kafka Testcontainers: broker in Docker

### 8.1. Lifecycle model

Testcontainers manages containers according to the test lifecycle:

```text
JUnit starts
    |
    v
Testcontainers checks Docker
    |
    v
Starts Kafka image
    |
    v
Waits for broker readiness
    |
    v
Exposes mapped bootstrap address
    |
    v
Spring Boot KafkaTemplate / listener
    |
    v
Runs assertions
    |
    v
Container cleanup
```

Kafka runs in a separate process/container, yet the test still needs valid producer/consumer configuration. A container reporting "started" does not prove topics exist or consumers have assignments.

### 8.2. Container tests with `@DynamicPropertySource`

Example for Testcontainers **1.x** using `org.testcontainers.containers.KafkaContainer`. This API may be deprecated in newer releases; when upgrading Testcontainers, check the corresponding module/container class such as `org.testcontainers.kafka.ConfluentKafkaContainer` and version/image requirements.

`KafkaContainerIntegrationTest.java`:

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers(disabledWithoutDocker = true)
@SpringBootTest(classes = KafkaLabApplication.class)
@ActiveProfiles("test")
@Import(KafkaContainerIntegrationTest.TopicConfig.class)
class KafkaContainerIntegrationTest {

    private static final String TOPIC =
        "orders.container.it";

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"));

    @DynamicPropertySource
    static void kafkaProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
    }

    @Autowired
    OrderPublisher publisher;

    @Test
    void publishesAndConsumesUsingDockerKafka()
            throws Exception {

        Map<String, Object> props = new HashMap<>();
        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            kafka.getBootstrapServers());
        props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "tc-probe-" + UUID.randomUUID());
        props.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest");
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false);

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(props)) {

            consumer.subscribe(java.util.List.of(TOPIC));

            publisher.publish(
                TOPIC, "order-600", "CREATED")
                .get(10, TimeUnit.SECONDS);

            var received = KafkaTestUtils.getSingleRecord(
                consumer, TOPIC, Duration.ofSeconds(15));

            assertEquals("order-600", received.key());
            assertEquals("CREATED", received.value());
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TopicConfig {

        @Bean
        NewTopic ordersContainerTopic() {
            return TopicBuilder.name(TOPIC)
                .partitions(1)
                .replicas(1)
                .build();
        }
    }
}
```

A static `@Container` creates the container once per test class rather than starting/stopping per test method. `@DynamicPropertySource` supplies the port-mapped bootstrap servers to Spring Boot.

In the example, Testcontainers launches a real Kafka broker in Docker. `KafkaTestUtils.getSingleRecord` remains convenient for asserting consumer receipt; Testcontainers does not require Spring Kafka helpers, though since the test library is already included we can use them.

**Note:** `disabledWithoutDocker = true` lets environments without Docker skip the test instead of failing; on CI where the integration suite **must run**, omit this flag so the pipeline reports missing Docker as a configuration error. Never let critical tests be silently skipped in deployment pipelines.

### 8.3. `@ServiceConnection` in Spring Boot 3.1+

When adding the dependency:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

Spring Boot can auto-wire connection details from supported containers:

```java
@Container
@ServiceConnection
static KafkaContainer kafka =
    new KafkaContainer(DockerImageName.parse(
        "confluentinc/cp-kafka:7.6.1"));
```

Import:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
```

With matching configuration, you do not need to write `@DynamicPropertySource` for bootstrap servers manually.

**Pick one explicit mechanism** (`@ServiceConnection` or `@DynamicPropertySource`) to avoid ambiguity over which property wins. Support for container types depends on Boot/Testcontainers versions; check your release, especially when migrating to Testcontainers 2.x.

### 8.4. Never hard-code port 9092

Kafka containers expose an endpoint mapped by Docker to a random host port. Obtain it only via:

```java
kafka.getBootstrapServers()
```

Do not write `spring.kafka.bootstrap-servers=localhost:9092` to force connections; that can connect to the wrong Kafka on the host or fail on CI runners.

---

## 9. Putting Kafka and a database in the same integration test

A major reliability risk is **a consumer processing a record and then updating a database**. Unit tests mocking repositories do not verify real transactions or constraints.

Testcontainers can spin up:

```text
                 Docker runtime
           +----------------------+
           | KafkaContainer       |
           | topic: orders.events |
           +----------+-----------+
                      |
                      v
            Spring Boot @KafkaListener
                      |
                      v
           +----------------------+
           | PostgreSQLContainer  |
           | processed_event table|
           +----------------------+
```

### 9.1. Adding PostgreSQL Testcontainers

Dependencies:

```groovy
testImplementation 'org.testcontainers:postgresql'
testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
testRuntimeOnly 'org.postgresql:postgresql'
```

In real JDBC applications, `spring-boot-starter-jdbc` is usually `implementation`, not `testImplementation`. Place dependencies according to application architecture.

Example containers:

```java
@Container
static final KafkaContainer kafka =
    new KafkaContainer(DockerImageName.parse(
        "confluentinc/cp-kafka:7.6.1"));

@Container
static final PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>(
        DockerImageName.parse("postgres:16-alpine"))
        .withDatabaseName("reliability")
        .withUsername("test")
        .withPassword("test");

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.kafka.bootstrap-servers",
        kafka::getBootstrapServers);
    registry.add("spring.datasource.url",
        postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
        postgres::getUsername);
    registry.add("spring.datasource.password",
        postgres::getPassword);
}
```

When using a real database, provision schemas explicitly via Flyway/Liquibase or SQL initialization and verify each container's readiness. This is **test infrastructure**, not the complete listener/DAO program.

### 9.2. Key idempotency scenario

Target table:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    payload VARCHAR(1000) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

If the consumer reads the same event again (due to crash before offset commit, rebalance, or replay), the table must not contain two logical records for the same `event_id`.

PostgreSQL example:

```sql
INSERT INTO processed_event (
    event_id, order_id, payload
) VALUES (?, ?, ?)
ON CONFLICT (event_id) DO NOTHING;
```

If an additional business operation accompanies the event, the DB transaction must be designed to execute it once per event ID. `ON CONFLICT DO NOTHING` makes sense only when key-level deduplication is safe under the contract.

A test can send the same event ID twice and wait:

```java
await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertEquals(1L,
            jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM processed_event WHERE event_id = ?",
                Long.class, "evt-500")));
```

Also verify the **actual count of external side effects** if the consumer calls external services, not just row counts.

### 9.3. At-least-once and the Kafka/DB boundary

```text
Consumer polls event E
         |
         v
DB transaction commits event E
         |
         X  app crashes before offset commit
         |
         v
Consumer restarts and receives E again
```

In this sequence, Kafka can redeliver the event; that is normal at-least-once behavior. Kafka producer transactions or Kafka offset commits **do not automatically form an atomic transaction with an external PostgreSQL database**.

Therefore, in most database-updating consumers:

- Use a stable business/event key.
- Make DB writes idempotent.
- Commit offsets per matching listener semantics, **after** business handling succeeds.
- Consider transactional outbox when another event must also be emitted.
- Test crash windows and duplicate replays, not just happy paths.

---

## 10. Retries and dead-letter topics: tests must observe the final outcome

### 10.1. What is a poison message?

A message with a mismatched payload type, missing required fields, or violated invariant causing the listener to throw exceptions repeatedly:

```text
Kafka topic
  |
  +-- record A: valid  -> processed
  +-- record B: poison -> exception
  +-- record C: valid  -> stalled if B retries forever
```

The goal is **bounded retries**, followed by routing B to a DLT (or defined recovery mechanism), so C can proceed without losing B for investigation.

### 10.2. Configuring `DefaultErrorHandler`

In Spring Kafka 3.x, a common setup is:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlingConfig {

    @Bean
    DefaultErrorHandler commonErrorHandler(
            KafkaTemplate<String, String> template) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                template,
                (record, exception) ->
                    new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));

        // Two retries after initial attempt: at most
        // three processing attempts with this configuration.
        return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(100L, 2L));
    }
}
```

Create topics `orders.fail.it` and `orders.fail.it.DLT`. With a resolver preserving the source partition, the DLT must have **at least as many partitions** as the source. One source partition and one DLT partition keep tests simple.

### 10.3. Listener intentionally throwing an error

```java
@KafkaListener(
    id = "failing-order-listener",
    topics = "orders.fail.it",
    groupId = "orders-fail-it"
)
public void listen(ConsumerRecord<String, String> record) {
    if ("POISON".equals(record.value())) {
        throw new IllegalArgumentException(
            "Unprocessable payload");
    }

    // Normal business processing
}
```

This snippet is a method inside a Spring-managed bean, not a standalone method outside a class.

### 10.4. Test scenario

```text
topic: orders.fail.it
DLT:   orders.fail.it.DLT

Send key=order-bad, value=POISON
    |
    v
Listener throws
    |
    v
DefaultErrorHandler retries within configured budget
    |
    v
DeadLetterPublishingRecoverer publishes DLT record
    |
    v
Test consumer reads DLT:
  key = order-bad
  value = POISON
  headers contain error info/original topic depending on version
```

With `@EmbeddedKafka`:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = {
        "orders.fail.it",
        "orders.fail.it.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

A test can create a dedicated DLT consumer before sending the poison message:

```java
Map<String, Object> props =
    KafkaTestUtils.consumerProps(
        "dlt-probe-" + UUID.randomUUID(),
        "false", embeddedKafka);

try (Consumer<String, String> dltConsumer =
        new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            new StringDeserializer()).createConsumer()) {

    embeddedKafka.consumeFromAnEmbeddedTopic(
        dltConsumer, "orders.fail.it.DLT");

    publisher.publish(
        "orders.fail.it",
        "order-bad",
        "POISON"
    ).get(10, TimeUnit.SECONDS);

    var dlt = KafkaTestUtils.getSingleRecord(
        dltConsumer,
        "orders.fail.it.DLT",
        Duration.ofSeconds(20));

    assertEquals("order-bad", dlt.key());
    assertEquals("POISON", dlt.value());
}
```

**Companion setup required:** the listener bean, `DefaultErrorHandler` bean, String serializers/deserializers, and both topics must all reside in the same Spring test context. The snippet above illustrates assertion structure rather than a standalone executable fragment.

### 10.5. Do not confuse broker ack with listener recovery

A successful `KafkaTemplate.send(...).get(...)` only states that **the input record was accepted by the broker**. A DLT record appearing proves the recovery path ran. When verifying that a message was processed after retries or routed to the DLT, assert one of those outcomes, **never rely on the send future**.

### 10.6. Test failure types and attempt counts

A reliability test should also measure:

- How many times the listener was invoked for the poison message.
- Retries with backoff or a no-retry policy for permanent errors.
- DLT receiving exactly one logical record per event ID.
- Original topic/partition/offset headers and exception metadata if needed for audits.
- Valid records after the poison pill still processing per policy.
- If the DLT is unavailable, how the error handler handles recovery failures.
- When deserialization fails **before the listener**, whether `ErrorHandlingDeserializer`/dedicated handling is used.

Verify these outcomes against your deployed Spring Kafka version's behavior; never assume every exception goes through the exact same listener error handler.

---

## 11. Deserialization errors differ from listener errors

### 11.1. Why was the listener never called?

Normal pipeline:

```text
Kafka bytes
    |
    v
Deserializer
    |
    +-- failure before creating object
    |
    v
ConsumerRecord<K,V>
    |
    v
@KafkaListener
    |
    +-- business exception
```

A `JsonDeserializer` can fail to construct an object from a bad payload. When using a deserializer directly without proper error capture, the listener method never receives the record; tests throwing exceptions inside the listener do not exercise this stage.

### 11.2. `ErrorHandlingDeserializer`

Spring Kafka provides `ErrorHandlingDeserializer` to preserve deserialization error details in headers and let container error handling act per configuration.

Illustrative properties:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
```

With JSON, configure type mappings/trusted packages matching application schemas; never enable wildcard `*` trusted packages unconditionally in environments accepting untrusted input.

### 11.3. Essential integration test case

Test an invalid JSON payload:

1. Producer sends unparseable bytes.
2. Consumer is configured with `ErrorHandlingDeserializer`.
3. Verify the business listener does not treat that payload as a valid object.
4. Error handler routes the record to the DLT or follows the recovery policy.
5. Assert the DLT retains payload/headers per design without stalling the partition forever.

**Limitation:** serializing DLT payloads when value deserialization failed may require a producer supporting `byte[]` and JSON or an appropriate configuration. Do not assume `KafkaTemplate<String,String>` can write every failed record's raw bytes. In real integration suites, design recoverer/serializer mappings for both valid payloads and un-deserialized raw bytes.

---

## 12. Testing offsets, replays, and delivery semantics

### 12.1. Offsets belong to the consumer group

A topic has multiple partitions; each group tracks committed offsets independently per partition:

```text
topic orders.events partition 0
  offset 0: E1
  offset 1: E2
  offset 2: E3
  offset 3: E4

group = orders-projection
  committed offset = 2
  => after restart, may process starting at offset 2
     (next record per offset-commit semantics)
```

Kafka committed offsets represent the **next position to read** in each partition, not directly a "uniquely processed message ID."

### 12.2. Testing replays from crash windows

A meaningful scenario:

```text
E1 -> listener receives
   -> business DB commit succeeds
   -> process killed before offset commit
   -> listener restarts with same group
   -> E1 may be delivered again
```

Tests must verify:

- The Kafka offset had not committed at crash time.
- After restart, the same consumer group re-reads E1.
- The handler relies on unique `eventId`, creating no duplicate business rows.
- If downstream events exist, no duplicate business effects violate the contract.

Do not merely call the listener method twice with Mockito and claim end-to-end at-least-once; include a real Kafka consumer group and real offset state in at least one integration test.

### 12.3. Ack modes and commit timing

Spring Kafka listener containers support ack modes such as `RECORD`, `BATCH`, `MANUAL`, and `MANUAL_IMMEDIATE`. Offset commit behavior differs by configuration, consumer transactions, and error handlers.

Example with manual ack:

```yaml
spring:
  kafka:
    listener:
      ack-mode: manual_immediate
```

The listener can accept `Acknowledgment`:

```java
@KafkaListener(
    topics = "orders.manual.it",
    groupId = "orders-manual-it"
)
public void onMessage(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    businessService.persistIdempotently(record);
    acknowledgment.acknowledge();
}
```

Import:

```java
import org.springframework.kafka.support.Acknowledgment;
```

Ack only **after** the business operation succeeds per contract. Still, acking and DB commits remain two distinct systems; a crash at the boundary can trigger a replay. Tests must rely on idempotency rather than assuming system-wide exactly-once.

### 12.4. When is `seek` needed in tests?

To test replaying a record at a specific offset, a test can assign the partition and `seek` to the target offset. When doing so, a manual consumer does not fully simulate group rebalances/commits, so a separate test running a real consumer group is still needed.

Distinguish clearly:

- **Seek test:** verifies the handler is idempotent when a record is re-read.
- **Group restart test:** verifies offset commit, assignment, and rebalance lifecycles.
- **Broker failover test:** verifies recovery when a partition leader changes or connections drop.

Never use a single seek test as proof for all three.

---

## 13. Testing ordering, partitions, and concurrency

### 13.1. Kafka guarantees ordering only within a partition

Example:

```text
Topic orders.events, 3 partitions:

partition 0: E1 -> E4 -> E7
partition 1: E2 -> E5
partition 2: E3 -> E6
```

Consumers in the same group can process partitions in parallel. Kafka does not guarantee a total order across partitions. If business rules require events for the same order to follow sequence, producers should use **the same key** for that order's events so they route deterministically to one partition.

### 13.2. Testing per-key ordering

Scenario:

1. Create a 3-partition topic.
2. Send `ORDER_CREATED`, `ORDER_PAID`, `ORDER_SHIPPED` with the same key `order-777`.
3. Wait for the consumer to receive all three.
4. Assert ordering of the three same-key records by partition offset.
5. Verify they landed in the same partition.

Do not assert a "global total order" across records with different keys on multiple partitions; Kafka provides no such general guarantee.

### 13.3. Testing concurrency and rebalances

With `@KafkaListener(concurrency = "3")` on a 3-partition topic, up to three consumer instances can run concurrently. Yet tests must consider:

- Consumer group assignment.
- Actual partition count.
- When listeners start and join the group.
- Listener thread safety.
- Shared DB writes/unique constraints.
- Rebalances when adding/removing consumers.

Raising concurrency does not split a single partition's records arbitrarily across multiple consumers **in the same group**; each partition is assigned to one consumer in the group at a time per group protocol.

### 13.4. Retries can affect partition progress

If the first record on a partition keeps failing and the error handler seeks/retries, subsequent records on the same partition can be delayed. Tests should not assert only the poison record's DLT entry; send a valid record after it and confirm progress resumes per policy.

---

## 14. Testing producer reliability: acks, timeouts, and duplicates

### 14.1. Settings to understand

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 5
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
```

This is an illustrative configuration, not an optimal setting for every workload. With modern Kafka clients, idempotent producers may be enabled by default when settings permit; explicit configuration helps learners see the intent.

- `acks=all`: leader waits for ISR replicas per broker/topic policy.
- `enable.idempotence=true`: reduces duplicates from producer retries within Kafka producer session/sequence semantics.
- `retries`: retries eligible retriable errors.
- `delivery.timeout.ms`: overall time budget the producer spends on delivery, including retries per client semantics.
- `max.in.flight.requests.per.connection` relates to ordering and idempotence.

### 14.2. Single-broker does not prove replication

In single-broker Testcontainers, topics have `replicas=1`. `acks=all` here only receives an ack from the lone existing ISR; it cannot prove data survives when **another broker** fails over.

To test losing a partition leader while the system stays up, build a multi-broker cluster with an appropriate replication factor, realistic `min.insync.replicas`, and leader/ISR checks.

### 14.3. Producer idempotence does not replace consumer idempotence

Producer idempotence prevents certain duplicates when the producer retries the same record. Yet an application calling `send` twice because an HTTP request was retried still creates two business events. Consumer replays after offset commit failures can also cause repeated processing. Hence business event IDs and database uniqueness remain vital.

---

## 15. Testcontainers for failure injection

### 15.1. Faults to simulate

| Fault | Why it is needed | What to assert |
| --- | --- | --- |
| Broker unavailable at startup | Producer/consumer connect late | App does not report false success; retries or reports readiness properly |
| Broker temporarily unreachable | Network timeouts | Producer future reports right error/timeout; consumer recovers within budget |
| Broker restart | TCP connections severed | Clients reconnect without losing events per retention/offsets |
| DB temporarily unavailable | Consumer persistence fails | Never acks falsely; idempotent retry/replay |
| Listener process dies | Uncommitted offsets | Record replays with no duplicate output |
| Poison message | Handler throws repeatedly | Retries exhausted → DLT, then continues |
| Rebalance | Consumer membership changes | Assignments/offsets accurate; no bugs from shared state |
| DLT producer fails | Recovery path unavailable | Never silently commits offsets or drops records |
| High network latency | Slow request/response | Timeouts, backoff, and SLAs respected |

### 15.2. Using Toxiproxy when cutting networks is needed

Multi-container topology:

```text
Spring application
        |
        v
   Toxiproxy
    /    \
   /      \  latency, bandwidth limit,
  /        \ connection cut
 v
Kafka broker
```

Testcontainers supports a Toxiproxy container to inject faults into TCP connections. However, Kafka uses **advertised listeners**: clients fetch bootstrap metadata and then connect directly to advertised broker addresses, bypassing the proxy if topology is misconfigured.

Therefore, Kafka network-partition tests must configure advertised endpoints and client/broker routing properly. Proxying only the bootstrap port does not guarantee subsequent connections pass through the proxy.

### 15.3. Do not stop and restart containers arbitrarily

If `KafkaContainer` is `stop()`ped and `start()`ed mid-test, Docker may assign a **different mapped host port**. The Spring context already cached the old bootstrap address from `@DynamicPropertySource` at startup; clients targeting the old endpoint may never recover.

When testing broker restarts:

- Use fault injection that keeps advertised endpoints stable, or
- Restart the Spring context/datasource clients when endpoints change, or
- Build a fixed Docker network topology and test connectivity accordingly.

Do not mistake broken test container lifecycle handling for a Kafka retry bug.

### 15.4. Use finite timeouts

During fault injection, a producer send or consumer poll can block until timeout. Tests must set explicit limits:

```java
var future = publisher.publish(
    "orders.container.it", "order-x", "DATA");

assertThrows(
    java.util.concurrent.TimeoutException.class,
    () -> future.get(100, TimeUnit.MILLISECONDS));
```

This is merely an **assertion-pattern illustration**: on a specific Kafka client and CI host, a send might finish quickly or fail with a different exception; never treat 100 ms as a universal truth about broker outages. Stable tests control the fault, know when the endpoint was cut, and assert the designed outcome (success, failure, or deadline exceeded) against application SLAs.

---

## 16. Testing transactions and exactly-once accurately

### 16.1. Kafka transactions apply to Kafka records/offsets

Spring Kafka supports transactional producers and listener containers to coordinate Kafka transactions in matching flows, such as consuming one topic and publishing to another in the same Kafka transaction.

To test transactional producers in a **single-broker test**, internal transaction state topics typically need replication factor and ISR settings matching one broker:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.tx.input", "orders.tx.output"},
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

Spring Kafka transaction configs also require a transaction ID prefix and version-matched listener container transaction manager/transactional producer. Enabling a few `brokerProperties` alone does not give a job exactly-once processing.

### 16.2. Testing `read_committed` consumers

For transactional Kafka records, consumers read using:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

Tests should distinguish:

- Transaction commit: record becomes visible to `read_committed`.
- Transaction abort: record remains invisible to `read_committed`.
- Kafka-to-Kafka processing: output records and consumed offsets commit in the same Kafka transaction when EOS is configured properly.
- Non-Kafka business databases: zero automatic atomicity between a Kafka transaction and a PostgreSQL local transaction.

### 16.3. Exactly-once does not mean "every side effect runs once"

Kafka EOS protects a specific Kafka transaction boundary. If a consumer sends an email or creates a payment on a remote API and then crashes, Kafka transactions do not undo the email/payment. Reliability tests must make "exactly-once" concrete:

- Exactly-once **Kafka output records** within a supported processing topology.
- At-least-once delivery with **idempotent DB projections**.
- Exactly-once **business effects** via idempotency keys supported by target systems.

Never use a single-broker embedded test to claim every production side effect executes strictly once.

---

## 17. Making tests repeatable: preventing flaky integration tests

### 17.1. Common causes of flakiness

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Producer send succeeds yet listener misses it | Consumer not assigned yet | `ContainerTestUtils.waitForAssignment` or condition wait |
| Consumer misses earlier messages | `auto.offset.reset=latest`, new group subscribed late | `earliest` for fixtures or assign before sending |
| Test reads another test's records | Shared topic/group | Dedicated fixture topics, fresh consumer groups |
| Test receives two unexpected records | Retries/replays or leftover topic data | Assert by event ID, isolation, and cleanup |
| Test hangs forever | Poll/get without timeout | Finite timeouts with diagnostic failures |
| CI lacks Docker | Container cannot start | Docker-enabled runners, split integration suites |
| Testcontainers image pull too slow | Uncached image/slow network | Pin images, cache Docker layers where possible |
| Context connects to `localhost:9092` | Bootstrap property not overridden | `bootstrapServersProperty` or `@DynamicPropertySource` |
| DLT test gets no record | Missing topic/partitions, wrong serializer | Create DLT, check recoverer/factory |
| JSON deserialization fails before listener | Error handler not handling deserialization stage | `ErrorHandlingDeserializer` and matching DLT serializer |
| Tests interfere with each other | Shared Spring context/broker state | Independent fixtures; selective `@DirtiesContext` |
| Test asserts too early | Kafka is asynchronous | Poll/latch/Awaitility on conditions |
| Passes locally, fails under high CI load | Tight timing thresholds, CPU throttling | Bounded timeouts, observe assignment/readiness |
| Broker stop/start changes endpoint | Docker mapped port changed | Stable proxy or restart context |
| Ordering test fails | Comparing across multi-partition topic | Assert per partition/per key |
| Container test skipped unnoticed | `disabledWithoutDocker=true` | Require Docker on critical CI suites |

### 17.2. Use event IDs to avoid wrong assertions

Do not assert "listener received any one message." Send a unique key/event ID:

```java
String eventId = "it-" + UUID.randomUUID();
publisher.publish(TOPIC, eventId, "CREATED");
```

The test consumer looks for that exact key. However, a random ID **inside a test** to isolate fixtures differs from generating random UUIDs as business event identities in production. Real business event IDs must remain stable across retries/replays.

### 17.3. Timing topic and listener creation

With `@EmbeddedKafka(topics=...)`, the broker creates topics before test methods run. With Testcontainers + `NewTopic`, `KafkaAdmin` creates topics when the application context starts. Tests must ensure **topics already exist** before sending if auto-create is disabled.

Having a listener bean does not mean partition assignment is complete. If a test must synchronize with the listener, wait for readiness via registry/container before sending.

### 17.4. Tests must never rely on JUnit execution order

One test setting up a topic and another reading it will fail when run in isolation. Each test should set up its own prerequisites or use clear `@BeforeAll`/`@BeforeEach` lifecycles. Under parallel execution, isolate by class/topic/group so shared state cannot race.

### 17.5. Assert final outcomes through meaningful outputs

For a consumer turning events into database projections:

```text
Test sends event E
  |
  v
Kafka listener processes async
  |
  v
Await database projection update
  |
  v
Assert business key + fields + unique count
```

This is far more trustworthy than asserting a boolean flag inside the listener set by the test itself without exercising real persistence logic.

---

## 18. Organizing test suites and CI

### 18.1. Grouping by purpose

A sensible layout:

```text
src/test/java/
  Unit:
    OrderMapperTest
    ValidationRuleTest

  Embedded integration:
    EmbeddedKafkaIntegrationTest
    ListenerIntegrationTest
    KafkaDltIntegrationTest

  Container integration:
    KafkaContainerIntegrationTest
    KafkaPostgresIntegrationTest

  Reliability/fault injection:
    KafkaOutageIT
    KafkaConsumerReplayIT
    BrokerFailoverIT
```

Note that the `*IT` naming is a convention to distinguish integration tests; Gradle does not automatically create separate source sets/tasks from names alone. For an independent `integrationTest` task, configure `sourceSets`/tasks explicitly and invoke them in CI.

### 18.2. Execution strategy

| When to run | Recommended tests | Reason |
| --- | --- | --- |
| Every commit / small PR | Unit + selective Embedded Kafka | Fast feedback |
| Pull request to main | Unit + Embedded + Kafka container | Catches wiring/dependency bugs |
| Pre-release | Kafka + DB + DLT/replay/transaction scenarios | Proves failure paths |
| Scheduled / nightly | Multi-container chaos, network faults, broker restarts | High cost and environmental prerequisites |
| Staging / preproduction | ACLs, TLS, multi-broker, retention, ISR, load | Close to production topology |

Do not let multiple CI jobs share a single Kafka broker; that increases test-data overlap and makes debugging hard.

### 18.3. Docker images and versions

Pin images instead of using `latest`:

```java
DockerImageName.parse("confluentinc/cp-kafka:7.6.1")
```

This keeps tests consistent when upstream publishes new Kafka images. Still, **schedule planned version upgrades** to catch client/broker compatibility issues; pinning forever is not a safe long-term strategy.

### 18.4. Optimizing CI runtime

- Use static containers per test class when methods are well isolated.
- Never start Docker for unit tests.
- Share one Kafka container per integration class where appropriate.
- Minimize unnecessary Spring context rebuilds.
- Use Awaitility and assignment waits instead of long sleeps.
- Cache Docker images on CI runners where policy allows.
- Enable Testcontainers reusable containers on developer laptops only when state-leakage risks are understood; never rely on reusability as a safe CI default.

### 18.5. Collecting evidence on test failure

A useful integration failure report includes:

- Topic, partition, offset, and record key/event ID.
- Container logs and Kafka broker errors.
- Consumer group/assignments and committed offsets where relevant.
- Spring Kafka listener exception stack trace.
- Retry attempts, DLT topic/headers.
- DB row states, transaction outcomes, and idempotency checks.
- Versions of Java, Boot, Spring Kafka, Kafka image, and Testcontainers.
- Timeouts and fault-injection timestamps.

Avoid leaking secrets, full PII payloads, and credentials from container logs into public CI artifacts.

---

## 19. A pragmatic reliability test matrix

Do not try to call one test "the reliability test" and expect it to cover everything. A matrix for an order-event system:

| ID | Scenario | Environment | Core assertion |
| --- | --- | --- | --- |
| R01 | Producer sends String record | Embedded | Broker receives right topic/key/value |
| R02 | `@KafkaListener` receives event | Embedded | Listener business side effect is accurate |
| R03 | Valid JSON payload | Embedded/container | Deserializes into domain object |
| R04 | Invalid JSON | Embedded | Error handler/DLT captures failed bytes/headers properly |
| R05 | Listener transient failure then success | Embedded | Bounded attempts; right output |
| R06 | Poison record exhausted | Embedded | DLT holds record; partition not stalled forever |
| R07 | Listener crashes after DB commit | Kafka + PostgreSQL | Replay does not duplicate DB business effect |
| R08 | Brief broker disconnect | Container + proxy | Client recovers or fails per SLA |
| R09 | Prolonged broker outage | Container + proxy | Timeout/backoff; no false success |
| R10 | Same key sends multiple events | 3-partition broker | Per-key ordering |
| R11 | Consumer rebalance | Container/multi-consumer | Assignments and offsets drop zero records |
| R12 | Kafka transaction abort | Transaction-enabled broker | `read_committed` consumer sees no aborted output |
| R13 | DLT unavailable | Broker/container fault | Never silently drops records |
| R14 | Deployment compatibility | Image/cluster version matrix | Client/serializer/schema compatibility |
| R15 | Cluster leader failover | Multi-broker Kafka | Recovery and durability per ISR policy |

Not every scenario is adequately tested by single-node Embedded Kafka. Match test environment realism to each row of the matrix.

---

## 20. Hands-on project: tiered exercises

### Exercise 1 — Testing producer on Embedded Kafka

Build `OrderPublisher` sending records to `orders.embedded.it`. Use `@EmbeddedKafka` and an independent test consumer.

Requirements:

- Bootstrap address comes from the embedded broker.
- Assert topic/key/value.
- Send multiple records with different keys to observe partitions.
- Never use `Thread.sleep`.
- Close the consumer after the test.

### Exercise 2 — Testing listener with business data

Write a `@KafkaListener` receiving `OrderEvent` and calling a repository to save state. Use `@EmbeddedKafka` and test with `await().untilAsserted(...)` on the repository.

Requirements: data persists accurately, listener assignment is ready, and tests do not depend on test method execution order.

### Exercise 3 — Moving tests to Testcontainers

Replace Embedded Kafka with `KafkaContainer` and `@DynamicPropertySource`. Declare `NewTopic` in test config.

Requirements:

- Pinned Kafka image.
- Never hard-code `localhost:9092`.
- Tests run on Docker CI runners.
- Decide fail vs. skip when Docker is absent per suite policy.

### Exercise 4 — Retries then DLT

Listener throws an exception when payload equals `POISON`. Configure `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`.

Requirements:

- Bounded attempts.
- DLT receives the right key/value.
- Appropriate tracing headers.
- Subsequent valid records still get processed.
- Never hard-code sleeps to wait for the DLT.

### Exercise 5 — DLT for deserialization failures

Producer sends invalid JSON bytes; consumer uses `ErrorHandlingDeserializer`. Configure matching recoverer and DLT serializers.

Requirements: business listener never receives bad objects, DLT keeps enough info for analysis, and consumer does not retry infinitely.

### Exercise 6 — Idempotent DB projection

Use Kafka + PostgreSQL Testcontainers. Write a listener persisting `eventId` into a table with a unique constraint; send the same event ID twice.

Requirements: only one business record exists; also test replay after a simulated crash before offset commit.

### Exercise 7 — Per-key ordering

Create a 3-partition topic. Send `CREATED`, `PAID`, `SHIPPED` for the same order key. Assert ordering by offset without demanding ordering across different keys on different partitions.

### Exercise 8 — Broker/network outage

Use Kafka Testcontainers and a fault-injection proxy configured with proper advertised listeners. Cut the network while the producer sends.

Requirements: app reports accurate status, bounded retry/backoff occurs, and after recovery, records/DB outputs reconcile by event ID.

### Exercise 9 — Transactional Kafka flow

Build a processor consuming topic A and publishing topic B inside a Kafka transaction, with a record triggering an exception. Verify `read_committed` sees only committed outputs and offsets per EOS config.

Explain the boundary with PostgreSQL/HTTP side effects, without claiming exactly-once across external systems.

### Exercise 10 — Running tests on CI

Separate Embedded Kafka and Testcontainers groups. Configure timeouts, logs, versions, and Docker image caching. Intentionally fail one test to verify artifacts/logs contain enough debugging data.

---

## 21. Checklist before trusting a Kafka integration test

- [ ] Test starts a real Kafka broker without accidentally connecting to an external environment broker.
- [ ] Bootstrap servers come from `@EmbeddedKafka` or Testcontainers, never hard-coded ports.
- [ ] Topics and partitions are created deterministically.
- [ ] Consumer group/offset isolation is clear, free of records from other tests.
- [ ] Test synchronizes on listener readiness or waits on business output with timeouts.
- [ ] Does not rely on fixed sleeps or JUnit method order.
- [ ] Asserts not just producer acks, but **consumer effects** where required.
- [ ] Covers success, transient failures, permanent failures, and DLTs.
- [ ] Includes replay/duplicate and business idempotency tests.
- [ ] Does not equate `acks=all` on one broker with replication durability.
- [ ] Clearly documents boundaries between Kafka transactions and DB transactions.
- [ ] When testing network faults, advertised listeners actually route through the fault-injection path.
- [ ] Container logs and exception context are collected on CI failures.
- [ ] Kafka client/broker, Spring Kafka, and Testcontainers versions are controlled.
- [ ] Security, multi-broker failover, and heavy load tests live at the appropriate tier.

## 22. Conclusion

**Embedded Kafka** is ideal for fast, real testing of Spring Kafka flows `KafkaTemplate → broker → consumer/@KafkaListener`, especially when a compact, Docker-free test suite is desired. **Testcontainers** runs a broker inside Docker and provides a clean foundation for adding databases, network proxies, and distributed components to integration tests.

For reliability, the ultimate question is not "did the test receive a message," but rather:

- When a listener fails, is the message retried properly or routed to the DLT?
- When crashing at the commit boundary, is business data duplicated?
- When a broker or database disconnects, does the application time out, retry, and recover within bounds?
- When a consumer group rebalances, is per-partition ordering preserved with zero lost events?
- When tests re-run on CI, are results stable with enough evidence to debug?

A reliable Kafka system requires **multiple test layers**, each proving its exact scope. Embedded Kafka and Testcontainers do not completely replace each other; they complement each other to catch bugs before they surface in production.

## 23. References

- [Spring for Apache Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `KafkaTestUtils`, and listener tests.
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler` and recoverers.
- [Spring for Apache Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): `@RetryableTopic` and retry/DLT topologies.
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): Kafka transactions and Kafka-scoped exactly-once.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Kafka auto-configuration and properties.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` and container test setup.
- [Testcontainers for Java — Kafka Module](https://java.testcontainers.org/modules/kafka/): `KafkaContainer`, `ConfluentKafkaContainer`, and image compatibility.
- [Testcontainers for Java — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): network fault injection.
- [Apache Kafka Documentation — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): group IDs, offset resets, and isolation levels.
- [Apache Kafka Documentation — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): acks, retries, idempotence, and delivery timeouts.
