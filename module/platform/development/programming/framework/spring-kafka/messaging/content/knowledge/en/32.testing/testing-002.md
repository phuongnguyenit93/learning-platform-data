# spring-kafka-test and Testing Starters

Testing a Spring Kafka application requires verifying more than just whether a method was called. A real messaging flow involves a producer sending a record, the broker storing it into a topic/partition, the consumer receiving the record, deserializing the payload, invoking the listener, and committing the offset. The right testing toolkit helps verify each layer of this flow with varying cost and confidence.

`spring-kafka-test` provides an embedded Kafka broker, utilities for creating test producers/consumers, record-reading helpers, matchers, and mock factories. With Spring Boot, the Kafka testing starter bundles the dependencies needed to run integration tests. Combine them with JUnit Jupiter, AssertJ, and Mockito to verify both business logic and Kafka communication behavior.

This lesson focuses on choosing dependencies, initializing an embedded broker, using `KafkaTestUtils`, testing `KafkaTemplate` and `@KafkaListener`, distinguishing mocks from real brokers, and organizing stable tests in CI.

## 1. Testing Layers in a Spring Kafka Application

Not every test needs to start a Kafka broker. Choose the scope based on what needs to be verified.

| Test Type | Components Under Test | Appropriate Tools |
|---|---|---|
| Unit test | Business rules, mapping, validation | JUnit Jupiter, Mockito, AssertJ |
| Producer unit test | How the service calls `KafkaTemplate` and picks topic/key/headers | Mockito or `MockProducer` |
| Listener unit test | Event handling logic after the listener receives a payload | Direct method invocation, mocked dependencies |
| Kafka integration test | Serialization, publishing, consuming, partitions, headers, offsets | `spring-kafka-test` and embedded broker |
| Spring context integration test | Auto-configuration, listener container, dependency injection | `@SpringBootTest` and `@EmbeddedKafka` |
| Contract/system test | Schema compatibility, ACLs, TLS, cluster configuration, and multiple services | Kafka container/cluster tests and integration environment |

For example, if you need to verify that `OrderService` computes totals properly, no broker is needed. If you need to verify that `KafkaTemplate` sends the right key and topic, you can mock the template. If you need to verify that a listener actually deserializes JSON and receives headers from a broker, use embedded Kafka or a broker running in a container.

A good test has one clear objective: testing business logic or testing Kafka integration behavior. Avoid bringing a broker into every unit test because startup time and shared state make tests slow and hard to isolate.

## 2. Choosing Testing Dependencies

`spring-kafka-test` is the artifact containing Spring Kafka's specialized test utilities. It does not replace JUnit or Spring Test.

### Spring Boot 4.x

With Spring Boot 4, use the Kafka test starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

This starter brings Kafka testing utilities onto the test classpath and aligns versions with Spring Boot dependency management.

### Spring Boot 3.x and Older Boot Versions

Use `spring-kafka-test` alongside Boot's test starter:

```xml
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
```

If the project does not use Spring Boot, declare JUnit Jupiter/Spring Test as needed and add `spring-kafka-test` with a version compatible with `spring-kafka`.

Do not manually pick a `spring-kafka-test` version different from the runtime Spring Kafka version. Let Spring Boot dependency management handle it or declare a unified BOM/version.

### Gradle

Spring Boot 4.x:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
```

Spring Boot 3.x:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

After declaring the dependency, the IDE can import APIs such as:

- `org.springframework.kafka.test.context.EmbeddedKafka`
- `org.springframework.kafka.test.EmbeddedKafkaBroker`
- `org.springframework.kafka.test.utils.KafkaTestUtils`
- `org.springframework.kafka.test.utils.ContainerTestUtils`
- `org.springframework.kafka.test.hamcrest.KafkaMatchers`
- `org.springframework.kafka.test.assertj.KafkaConditions`

Exact package names and APIs may change across major versions. Check the Javadoc of the actual version in your dependency tree if the IDE cannot resolve an import.

## 3. JUnit Jupiter and Test Structure

Spring Kafka currently supports JUnit Jupiter. A basic test class uses `@Test`:

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderMapperTest {

    @Test
    void mapsOrderToEvent() {
        Order order = new Order("order-42", 125_000);

        OrderCreated event = OrderCreated.from(order);

        assertThat(event.orderId()).isEqualTo("order-42");
        assertThat(event.totalAmount()).isEqualTo(125_000);
    }
}
```

Unit tests do not need `@SpringBootTest` if they only test Java logic. If you need to inject Spring beans or verify configuration, use a Spring Test context.

Spring Kafka no longer supports JUnit 4; the examples in this lesson use JUnit Jupiter. When upgrading legacy projects, migrate runners/rules to the corresponding JUnit 5 extensions and annotations.

Commonly encountered annotations:

| Annotation | Purpose |
|---|---|
| `@Test` | Marks a test method |
| `@ExtendWith(MockitoExtension.class)` | Initializes Mockito in JUnit Jupiter |
| `@SpringBootTest` | Starts the Spring Boot application context |
| `@EmbeddedKafka` | Creates an embedded Kafka broker for testing |
| `@DirtiesContext` | Marks the context to be closed/refreshed after the test |
| `@TestConfiguration` | Adds beans dedicated to tests |
| `@DynamicPropertySource` | Registers dynamic properties from test fixtures |

Do not use `@SpringBootTest` out of habit for every test. Each context creation takes time and can start listener containers outside the scope of the test being run.

For producer services, you can use Mockito to verify `KafkaTemplate` calls without needing a broker:

```java
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.kafka.core.KafkaTemplate;

@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @InjectMocks
    OrderPublisher publisher;

    @Test
    void publishesOrderWithBusinessKey() {
        OrderCreated event = new OrderCreated("order-42");

        publisher.publish(event);

        verify(kafkaTemplate).send("orders", "order-42", event);
    }
}
```

This test verifies that the service picks the right topic and key. It does not verify that the broker received the record or that the serializer worked; those behaviors belong to integration tests.

## 4. What Is Embedded Kafka?

Embedded Kafka is a Kafka broker running inside the test process, managed by `spring-kafka-test`. Tests can send and read records as if connecting to a real broker.

Benefits:

- No separate Kafka server needs to be running on the developer machine.
- Topics and partition counts can be created per test.
- Serialization/deserialization can be tested over the Kafka protocol.
- `KafkaTemplate`, listener containers, keys, partitions, and headers can be verified.
- Tests can run in CI when the environment allows a local broker process.

Since Spring Kafka 3.1, there is a KRaft implementation `EmbeddedKafkaKraftBroker`. Spring Kafka 3.0/3.1 still had a legacy ZooKeeper implementation; with Kafka 4.0, ZooKeeper was removed and only KRaft remains.

In most tests, use the `@EmbeddedKafka` annotation so the framework creates the broker and registers the `EmbeddedKafkaBroker` bean.

## 5. Initializing an Embedded Broker with @EmbeddedKafka

Example with Spring Boot:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void embeddedBrokerStarts() {
        assertThat(embeddedKafka.getBrokersAsString())
            .isNotBlank();
    }
}
```

`@EmbeddedKafka` creates the `orders` topic with one partition. `bootstrapServersProperty` tells the broker to write its address to `spring.kafka.bootstrap-servers` for Spring Boot Kafka auto-configuration to use.

Since Spring Kafka 3.0.10, this property already defaults to `spring.kafka.bootstrap-servers` for Spring Boot applications. Declaring it explicitly in the example helps readers see the link between the embedded broker and client properties.

For tests using a Spring Test context, `EmbeddedKafkaBroker` can be injected as a bean. When not using a Spring context, JUnit Jupiter supports a parameter resolver:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@EmbeddedKafka(topics = "orders")
class StandaloneEmbeddedKafkaTest {

    @Test
    void exposesBrokerAddress(EmbeddedKafkaBroker broker) {
        assertThat(broker.getBrokersAsString()).isNotBlank();
    }
}
```

The standalone approach is useful when a test only needs a broker and does not need to start a Spring Boot context.

## 6. Configuring Brokers, Topics, and Partitions for Tests

You can create multiple topics and partitions:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = {
        "orders",
        "payments",
        "orders-dlt"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaFlowIntegrationTest {
    // Tests using the created broker and topics.
}
```

If custom broker properties are needed, use `brokerProperties` or `brokerPropertiesLocation`:

```java
@EmbeddedKafka(
    topics = "orders",
    brokerProperties = {
        "auto.create.topics.enable=false",
        "num.partitions=3"
    }
)
```

Properties must be valid Kafka broker configurations. Do not mistakenly put client properties such as `group.id` into `brokerProperties`.

If you want to create a topic with custom settings during a test, use `EmbeddedKafkaBroker.addTopics(...)` with `NewTopic`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@Autowired
EmbeddedKafkaBroker broker;

@Test
void createsTopicWithSeveralPartitions() {
    broker.addTopics(
        new NewTopic("audit-events", 4, (short) 1)
    );
}
```

With a single-node embedded broker, the replication factor must fit the number of running brokers. Never request a replication factor larger than the number of available brokers.

Use dedicated topics per test or per test class whenever possible. This prevents records from an earlier test from causing a later test to read unintended data.

## 7. Using KafkaTestUtils to Build Consumer Properties

`KafkaTestUtils` helps build consumer/producer configurations matching the embedded broker.

In Spring Kafka 4.0 and later, use the new overload:

```java
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> consumerProps =
    KafkaTestUtils.consumerProps(
        embeddedKafka,
        "orders-test-group",
        false
    );
```

This overload accepts the broker, group ID, and boolean `autoCommit`. It configures `bootstrap.servers`, default deserializers, and `auto.offset.reset=earliest`.

In Spring Kafka 3.x, the common overload is:

```java
Map<String, Object> consumerProps =
    KafkaTestUtils.consumerProps(
        "orders-test-group",
        "false",
        embeddedKafka
    );
```

In Spring Kafka 4.0, the older overload taking a string boolean was deprecated for removal. When upgrading major versions, migrate to the overload using a boolean with the broker first in the parameter list.

If key/value types other than the defaults are needed, override the serializer/deserializer:

```java
consumerProps.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
consumerProps.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
```

`auto.offset.reset=earliest` is useful when a test sends records before the consumer is created or before it subscribes. If the test should only receive new records after starting to consume, configure `latest` and explicitly control subscribe/send timing.

## 8. Creating Producers and Sending Records in Tests

Build producer properties with `KafkaTestUtils.producerProps`:

```java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> producerProps =
    KafkaTestUtils.producerProps(embeddedKafka);

producerProps.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class
);
producerProps.put(
    ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class
);
```

However, if the application already has a `KafkaTemplate` configured by Spring Boot, tests can inject the template and send records through it:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Test
void sendsRecord() throws Exception {
    kafkaTemplate.send(
        "orders",
        "order-42",
        "ORDER_CREATED"
    ).get(10, TimeUnit.SECONDS);
}
```

`KafkaTemplate.send` returns a `CompletableFuture<SendResult<K,V>>` in modern Spring Kafka versions. Use `get(timeout, unit)` in tests to wait for broker acknowledgment and ensure send errors are caught immediately during the test.

Do not just call `send` and end the test. If the test ends before the future completes, serializer or broker errors may surface too late and go uncaught by the test.

When send metadata needs verification, inspect `SendResult`:

```java
SendResult<String, String> result =
    kafkaTemplate.send("orders", "order-42", "ORDER_CREATED")
        .get(10, TimeUnit.SECONDS);

assertThat(result.getRecordMetadata().topic()).isEqualTo("orders");
assertThat(result.getRecordMetadata().partition()).isGreaterThanOrEqualTo(0);
assertThat(result.getRecordMetadata().offset()).isGreaterThanOrEqualTo(0);
```

If a test needs a specific partition, use the send overload taking a partition:

```java
kafkaTemplate.send(
    "orders",
    1,
    "order-42",
    "ORDER_CREATED"
).get(10, TimeUnit.SECONDS);
```

The topic must have the corresponding partition index. For example, `partition=1` requires the topic to have at least two partitions.

## 9. Reading Records with KafkaTestUtils

Create a consumer from properties and subscribe to the topic:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> props =
    KafkaTestUtils.consumerProps(
        embeddedKafka,
        "orders-read-test",
        false
    );

props.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
props.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);

Consumer<String, String> consumer =
    new KafkaConsumer<>(props);

try {
    embeddedKafka.consumeFromAnEmbeddedTopic(
        consumer,
        "orders"
    );

    kafkaTemplate.send(
        "orders",
        "order-42",
        "ORDER_CREATED"
    ).get(10, TimeUnit.SECONDS);

    ConsumerRecord<String, String> record =
        KafkaTestUtils.getSingleRecord(
            consumer,
            "orders",
            Duration.ofSeconds(10)
        );

    assertThat(record.key()).isEqualTo("order-42");
    assertThat(record.value()).isEqualTo("ORDER_CREATED");
}
finally {
    consumer.close();
}
```

`consumeFromAnEmbeddedTopic` assigns the consumer to a topic created by the embedded broker and by default seeks to the beginning of the partitions. Therefore, use a separate topic per test or call the overload with the `seekToEnd` parameter when needing to start from new records.

`getSingleRecord` waits for one record within the timeout. It fails if no record is received or if more than one record is received for that topic during the checked poll.

If a test can receive multiple records, use `KafkaTestUtils.getRecords(consumer, timeout)` and inspect `ConsumerRecords`:

```java
ConsumerRecords<String, String> records =
    KafkaTestUtils.getRecords(
        consumer,
        Duration.ofSeconds(10)
    );

assertThat(records.count()).isEqualTo(2);
assertThat(records.records("orders"))
    .extracting(ConsumerRecord::value)
    .containsExactlyInAnyOrder("ORDER_CREATED", "ORDER_CANCELLED");
```

Always set a finite timeout. Tests that wait indefinitely will hang CI when a broker or listener encounters an error.

## 10. Testing Listeners with Spring Boot and Embedded Kafka

To verify an end-to-end flow in an application context, start the real listener and send records to the broker.

Example listener:

```java
import java.util.concurrent.BlockingQueue;
import org.springframework.kafka.annotation.KafkaListener;

public class TestOrderListener {

    private final BlockingQueue<String> received;

    public TestOrderListener(BlockingQueue<String> received) {
        this.received = received;
    }

    @KafkaListener(
        id = "orders-test-listener",
        topics = "orders",
        groupId = "orders-integration-test"
    )
    public void onMessage(String payload) {
        this.received.add(payload);
    }
}
```

Test configuration and test class:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@SpringBootTest(properties = "spring.kafka.consumer.auto-offset-reset=earliest")
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderListenerIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    BlockingQueue<String> received;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void listenerReceivesPublishedMessage() throws Exception {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-test-listener");
        ContainerTestUtils.waitForAssignment(container, 1);

        kafkaTemplate.send(
            "orders",
            "order-42",
            "ORDER_CREATED"
        ).get(10, TimeUnit.SECONDS);

        String payload = received.poll(10, TimeUnit.SECONDS);

        assertThat(payload).isEqualTo("ORDER_CREATED");
    }

    @TestConfiguration
    static class TestBeans {

        @Bean
        BlockingQueue<String> receivedQueue() {
            return new LinkedBlockingQueue<>();
        }

        @Bean
        TestOrderListener testOrderListener(
                BlockingQueue<String> received) {
            return new TestOrderListener(received);
        }
    }
}
```

A queue helps synchronize the test with the listener without needing `Thread.sleep`. The test sends a record, waits up to 10 seconds, and verifies the payload the listener received.

In real projects, the listener can be a production bean injected with real dependencies or mocked downstream services. Use a dedicated consumer group for tests so it does not conflict with other listeners on the same broker.

When a test class uses `@SpringJUnitConfig`/a Spring Test context with an embedded broker, Spring Kafka documentation recommends considering `@DirtiesContext` to avoid a race during JVM shutdown where the broker closes while the context is still using it. With Spring Boot, apply this based on context lifecycle and how the suite reuses brokers; do not add the annotation mechanically because it forces the context to restart after each test class.

## 11. Waiting for Listener Assignment Before Sending Records

A common mistake is sending records as soon as a test begins, before the listener container has subscribed or been assigned partitions.

When a test needs to verify assignment, inject the container via the registry and use `ContainerTestUtils.waitForAssignment`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@Autowired
KafkaListenerEndpointRegistry registry;

@Autowired
EmbeddedKafkaBroker embeddedKafka;

@Test
void waitsUntilListenerIsAssigned() {
    MessageListenerContainer container =
        registry.getListenerContainer("orders-test-listener");

    ContainerTestUtils.waitForAssignment(
        container,
        embeddedKafka.getPartitionsPerTopic()
    );

    assertThat(container.isRunning()).isTrue();
}
```

The partition count parameter must match the assignment the test expects. With multi-consumer concurrency, do not assume every child receives partitions; total partitions and the consumer group determine distribution.

Waiting for assignment before publishing reduces timing-related flaky tests, especially when tests verify specific partitions, rebalances, offsets, or pause/resume.

## 12. Checking Keys, Partitions, Headers, and Timestamps

An integration test should check metadata if application logic depends on it.

Example:

```java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.core.KafkaTemplate;

ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "orders",
        0,
        "order-42",
        "ORDER_CREATED"
    );

record.headers().add(
    "correlation-id",
    "corr-123".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);
```

After reading the record:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.apache.kafka.common.header.Header;

assertThat(received.key()).isEqualTo("order-42");
assertThat(received.partition()).isZero();

// Correlation header:

Header correlationHeader =
    received.headers().lastHeader("correlation-id");

assertThat(correlationHeader).isNotNull();
assertThat(new String(
    correlationHeader.value(),
    StandardCharsets.UTF_8
)).isEqualTo("corr-123");
```

Check `partition` when the application requires key-based or partition-based routing. Checking only the payload can miss partition-selection bugs.

## 13. Testing Serialization and Deserialization

`spring-kafka-test` combined with an embedded broker helps verify real serializers/deserializers. This is especially important for JSON, Avro, Protobuf, or custom serializers.

Example JSON test:

1. Create a `KafkaTemplate<String, OrderCreated>` using the application's serializer.
2. Send an event to the topic.
3. Create a consumer using the matching deserializer.
4. Read the record and verify fields, schema version, and type.
5. Send an invalid payload if wanting to verify the error path.

Do not check only that JSON parses. Verify key contract details: field names, nullability, enums, timestamps, schema IDs/headers, and consumer compatibility.

With `ErrorHandlingDeserializer`, you can send invalid bytes and verify the deserialization error is placed in headers for the error handler to process. The listener may not be invoked in this case; observe the error path or a DLT consumer.

## 14. Testing Retries, Error Handlers, and DLT

Embedded Kafka can verify failure flows:

- Listener throws an exception on the first processing attempt.
- Error handler performs retries according to backoff.
- Listener succeeds on a subsequent attempt or the record is recovered.
- Permanently failed records are sent to the DLT.
- DLT records contain original metadata and required exception headers.

Do not use `Thread.sleep` to assume retries have occurred. Use `CountDownLatch`, `BlockingQueue`, Awaitility, or events/callbacks to wait for results with a finite timeout.

Tests should verify listener invocation count, recovery outcomes, and DLT contents. For retries with backoff, set wait durations matching the configured policy while avoiding overly broad timeouts that slow down the test suite.

## 15. MockProducer and MockConsumer When No Broker Is Needed

The Kafka client provides `MockProducer` and `MockConsumer`. Since Spring Kafka 3.0.7, `MockProducerFactory` and `MockConsumerFactory` make it easy to use them directly with `KafkaTemplate` and listener containers.

Use mocks when wanting to verify producer/consumer calling logic without a broker:

- `MockProducer` lets you inspect sent records.
- `MockConsumer` lets you inject fake records, control assignments, and control offsets.
- `MockProducerFactory` integrates with `KafkaTemplate`.
- `MockConsumerFactory` integrates with listener containers.

Example `MockProducerFactory`:

```java
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.mock.MockProducerFactory;

@Bean
ProducerFactory<String, String> mockProducerFactory() {
    return new MockProducerFactory<>(
        () -> new MockProducer<>(
            true,
            new StringSerializer(),
            new StringSerializer()
        )
    );
}
```

In tests, inject `MockProducer` or the factory to verify sent records. If the producer runs across multiple threads, the factory must return separate producer instances as appropriate; do not share a non-thread-safe mock producer across concurrent threads.

With a transactional mock producer, `initTransactions()` must be called before executing transactions. Spring Kafka provides `MockProducerFactory` constructors supporting transactional producers and transactional IDs.

Mocks do not fully simulate broker protocol, network serialization, partition leadership, transaction coordinators, or rebalances. When those behaviors must be verified, use an embedded broker or a broker container.

## 16. Distinguishing Embedded Kafka and Testcontainers

Both approaches can test integration, but with different goals:

| Criterion | Embedded Kafka | Testcontainers Kafka |
|---|---|---|
| Execution model | Embedded broker in the test process | Kafka running in a container |
| Startup | No Docker required | Requires Docker or a container runtime |
| Speed | Usually fast for component tests | Usually slower due to container startup |
| Cluster configuration | Suited for simple broker tests | More flexible with images/versions/configs |
| Production-like environment | Suited for basic protocol behavior | Can pick exact Kafka images and near-environment settings |
| CI | Requires allowing the broker to run in the JVM | Requires CI container support |
| Best suited for | Producer/listener, serialization, retry, DLT tests | Version compatibility, security, cluster topology, and production-like environment tests |

Embedded Kafka is a good choice for many integration tests in a module. Testcontainers is useful when testing specific Kafka images, multiple brokers, security configs, or interactions with other containers.

You do not need to run both for every test. Choose the tool based on what needs verification.

## 17. Managing Lifecycle and Sharing Embedded Brokers

Starting a separate broker for every test method usually makes the suite slow. Spring Test context caching and `@EmbeddedKafka` allow reusing a broker across a context's scope.

Principles:

- Prefer one broker for a group of integration tests sharing the same context.
- Use separate topics or ensure consumers seek to the right position.
- Use dedicated consumer group IDs so offset commits do not affect other tests.
- Close self-created consumers/producers in `try-with-resources` or `@AfterEach`.
- Close listener containers when a test creates containers manually.
- Avoid mixing a global embedded broker and per-class `@EmbeddedKafka` in the same suite because they share system properties and can conflict.

Spring Kafka 3.0+ includes `GlobalEmbeddedKafkaTestExecutionListener` for JUnit Platform, disabled by default. When enabling the global broker, configure topics, partitions, and broker properties via JUnit Platform/system properties. Do not mix the global broker with per-test-class brokers in the same suite without a clear design.

## 18. Avoiding Flaky Tests

Common causes:

| Symptom | Cause | Solution |
|---|---|---|
| Consumer does not receive sent records | Consumer starts after records are published while offset reset is latest | Use earliest or subscribe before sending |
| Test receives records from a previous run | Shared topics and groups | Separate topics/groups or explicit seeks |
| Test passes intermittently | Did not wait for listener assignment | `ContainerTestUtils.waitForAssignment` |
| Test times out | Unreasonable timeout or broker not ready | Wait on explicit conditions and log broker state |
| Receives more records than expected | Topic shared across tests | Isolate topics or filter by key/event ID |
| Context shutdown errors | Broker closes before context | Manage `@DirtiesContext` and lifecycle |
| Parallel tests collide on topics | Multiple tests share the same topic/group | Use unique topic/group names or limit parallelism |
| Test hangs CI | Infinite poll/await | Use finite Duration/timeouts |

Avoid using `Thread.sleep` as a synchronization mechanism. Use `CountDownLatch`, queues, Awaitility, or bounded polling to wait for real conditions.

## 19. Organizing Tests in a Project

Test sources can be split into groups:

```text
src
└── test
    ├── java
    │   └── com/example/messaging
    │       ├── unit
    │       │   ├── OrderServiceTest.java
    │       │   └── OrderMapperTest.java
    │       ├── producer
    │       │   └── OrderPublisherTest.java
    │       ├── listener
    │       │   └── OrderListenerTest.java
    │       └── integration
    │           ├── OrderKafkaIntegrationTest.java
    │           ├── RetryAndDltIntegrationTest.java
    │           └── SerializationIntegrationTest.java
    └── resources
        └── application-test.yml
```

Package names are only a suggestion. What matters is separating unit tests from integration tests so developers can run the fast group when editing logic and the broker test group when modifying Kafka configuration.

Example test profile:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Configuration in `application-test.yml` must fit the test cases. Do not apply one shared `AckMode` if certain tests need to verify different commit semantics.

## 20. Pre-Completion Test Suite Checklist

- Have `spring-kafka-test` or the Kafka test starter matching the Spring Boot version.
- Spring Kafka test version is compatible with runtime.
- Unit tests do not start a broker unnecessarily.
- Embedded Kafka is configured with explicit topics and partitions.
- Boot tests use the right `spring.kafka.bootstrap-servers`.
- Consumer groups and topics are isolated between tests.
- Consumer subscription/assignment completes before publishing when needed.
- `KafkaTestUtils` uses finite timeouts.
- Tests verify keys, partitions, headers, and payloads if they are part of the contract.
- Serialization/deserialization is tested with real serializers.
- Retries/DLT are tested with synchronization signals instead of sleep.
- Mock producers/consumers are used only for behaviors not requiring a broker.
- Consumers, producers, and listener containers are closed properly in lifecycle hooks.
- Suite does not arbitrarily mix global embedded brokers with per-class brokers.
- CI can run embedded brokers or containers according to the project strategy.

## 21. Key Takeaways

- `spring-kafka-test` adds specialized testing tools for Spring Kafka.
- Spring Boot 4 provides `spring-boot-starter-kafka-test`; earlier Boot versions typically use `spring-kafka-test` alongside `spring-boot-starter-test`.
- `@EmbeddedKafka` creates a real broker in the test process and can register its address into `spring.kafka.bootstrap-servers`.
- Kafka 4.0 uses only the embedded KRaft broker.
- `KafkaTestUtils` helps build producer/consumer properties and read records.
- In Spring Kafka 4, prefer the `consumerProps(embeddedKafka, group, autoCommit)` overload.
- `ContainerTestUtils.waitForAssignment` synchronizes tests with listener assignment.
- `MockProducerFactory` and `MockConsumerFactory` suit brokerless tests; they do not replace integration tests.
- Use dedicated topics/groups, finite timeouts, and synchronization signals to avoid flaky tests.
- Testing must verify the right layer under test: business logic, Spring context, or real Kafka communication.

By combining JUnit Jupiter, the testing starter, and `spring-kafka-test`, development teams can test messaging flows from producer to listener at reasonable cost. Unit tests keep feedback fast for business logic; embedded brokers confirm real Kafka behavior; and container tests fit scenarios needing production-like environments.

## References

- [Spring Kafka – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot – Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Kafka – KafkaTestUtils API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Kafka – EmbeddedKafkaBroker API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/test/EmbeddedKafkaBroker.html)
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/)



