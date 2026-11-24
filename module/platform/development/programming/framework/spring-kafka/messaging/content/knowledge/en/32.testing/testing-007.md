# Sending and Receiving Records in JUnit

Testing Kafka producers and consumers requires verifying both ends of the flow: the producer sends the right record to the topic, and the consumer receives the right key, value, headers, and required metadata. With Spring Kafka, you can use `spring-kafka-test` to run an embedded Kafka broker in JUnit, combining `KafkaTemplate`, `@KafkaListener`, and `KafkaTestUtils` utilities.

A good test distinguishes the moment the broker acknowledges publishing from the moment the listener finishes processing. `KafkaTemplate.send()` returns an asynchronous result; awaiting a successful future proves the broker acknowledged the record per producer configuration, but does not prove the consumer finished processing. To verify the consumer, wait for a signal from the listener such as a `BlockingQueue`, `CountDownLatch`, or Awaitility.

## 1. Choosing the Right Type of Test

Not every Kafka test needs to start a broker. Pick the test level based on the behavior to verify:

| Test Type | Components | Goal |
| --- | --- | --- |
| Unit test | Mockito, fake, or stub | Verify the service calls `KafkaTemplate` with expected topic, key, and payload |
| Integration test with Embedded Kafka | `@EmbeddedKafka`, `KafkaTemplate`, `@KafkaListener` | Verify serialization/deserialization, publishing, consuming, and listener container working together |
| Integration test with Testcontainers | Kafka container close to deployed broker | Test specific broker versions, transactions, security, ACLs, or real operational configuration |

`spring-kafka-test` provides an embedded broker and testing utilities. For scenarios needing verification of a specific Kafka broker version, SASL/SSL, KRaft, or transaction behavior in a production-like environment, Testcontainers is usually more suitable because it runs a broker image with a specific version.

## 2. Adding the Testing Dependency

With Maven, add `spring-kafka-test` in `test` scope:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

If the project uses Spring Boot dependency management, let the BOM manage compatible versions of Spring Kafka and `spring-kafka-test`. Avoid declaring a test library version different from the Spring Kafka version running in the application.

JUnit 5 is normally already included in Spring Boot's test starter. If the project does not use Spring Boot, include the matching JUnit Jupiter and Spring Test dependencies to use `@SpringJUnitConfig`.

## 3. Initializing Embedded Kafka in JUnit 5

`@EmbeddedKafka` creates a Kafka broker for the test and can pre-create topics. Combine it with `@SpringJUnitConfig` to load the Spring configuration containing the producer factory, consumer factory, and listener container factory.

The example below uses the `orders-it` topic with one partition. Both key and value are strings to focus on the record send/receive flow; when testing DTOs, replace the serializer/deserializer with the matching JSON or Avro ones.

```java
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.kafka.annotation.EnableKafka;

@Configuration
@EnableKafka
class KafkaTestConfiguration {

    @Bean
    ConsumerFactory<String, String> consumerFactory(
            EmbeddedKafkaBroker broker) {
        Map<String, Object> props = KafkaTestUtils.consumerProps(
                "orders-listener-group", "false", broker);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        return new DefaultKafkaConsumerFactory<>(
                props, new StringDeserializer(), new StringDeserializer());
    }

    @Bean
    ProducerFactory<String, String> producerFactory(
            EmbeddedKafkaBroker broker) {
        Map<String, Object> props = KafkaTestUtils.producerProps(broker);
        return new DefaultKafkaProducerFactory<>(
                props, new StringSerializer(), new StringSerializer());
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {
        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        return factory;
    }

    @Bean
    OrderTestListener orderTestListener() {
        return new OrderTestListener();
    }
}
```

`KafkaTestUtils.consumerProps()` and `producerProps()` retrieve bootstrap servers and suitable defaults from the embedded broker. `auto.offset.reset=earliest` helps the test consumer read from the beginning if no committed offset exists for the group. In tests sending records after the listener starts, this also avoids relying on stale offsets of a reused group.

## 4. Testing Producer Send and `@KafkaListener` Receive

Create a test-only listener. The listener pushes received records into a `BlockingQueue` so the test thread can wait for results without `Thread.sleep()`:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

class OrderTestListener {

    private final BlockingQueue<ConsumerRecord<String, String>> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            id = "orders-test-listener",
            topics = "orders-it",
            groupId = "orders-listener-group")
    public void onOrder(ConsumerRecord<String, String> record) {
        received.add(record);
    }

    public BlockingQueue<ConsumerRecord<String, String>> received() {
        return received;
    }
}
```

The listener bean is registered in `KafkaTestConfiguration`. Then write the JUnit 5 test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.kafka.support.SendResult;

@SpringJUnitConfig(classes = KafkaTestConfiguration.class)
@EmbeddedKafka(partitions = 1, topics = "orders-it")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderKafkaIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private OrderTestListener listener;

    @Test
    void sendsRecordAndListenerReceivesIt() throws Exception {
        SendResult<String, String> sendResult = kafkaTemplate
                .send("orders-it", "order-42", "ORDER_CREATED")
                .get(10, TimeUnit.SECONDS);

        assertNotNull(sendResult.getRecordMetadata());

        ConsumerRecord<String, String> received = listener.received()
                .poll(10, TimeUnit.SECONDS);

        assertNotNull(received, "Listener did not receive the record within the wait timeout");
        assertEquals("orders-it", received.topic());
        assertEquals("order-42", received.key());
        assertEquals("ORDER_CREATED", received.value());
        assertEquals(0, received.partition());
        assertEquals(0L, received.offset());
    }
}
```

In real configuration, `KafkaTestConfiguration` must declare the `OrderTestListener` bean as in the previous snippet. This bean can be placed in the same configuration class. The test context is closed after the class via `@DirtiesContext`; Spring manages the lifecycle of the listener container and producer factory.

`send(...).get(...)` waits for the broker to confirm publishing. `received().poll(...)` waits for the listener to actually receive the record. Do not replace these two steps with a single `Thread.sleep(1000)`: processing time depends on the test machine and broker load, so sleeping can both slow down tests and create intermittent failures.

Offset `0` in this example holds only when the topic was newly created, had no prior records, and only received this test record. If tests rerun on a shared topic, assert topic/partition/key/value or metadata under appropriate conditions instead of hard-coding offset `0`.

## 5. Inspecting Records Directly with KafkaTestUtils

If the goal is to verify that a producer wrote the right record to Kafka, you can create a separate test consumer and read the topic with `KafkaTestUtils`. This is useful when you do not need to start a Spring listener container.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Test
void producerWritesRecordToTopic() throws Exception {
    Map<String, Object> props = KafkaTestUtils.consumerProps(
            "orders-verification-group", "false", embeddedKafka);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    try (Consumer<String, String> consumer =
            new DefaultKafkaConsumerFactory<String, String>(
                    props,
                    new StringDeserializer(),
                    new StringDeserializer()).createConsumer()) {

        embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders-it");

        kafkaTemplate.send("orders-it", "order-99", "ORDER_CREATED")
                .get(10, TimeUnit.SECONDS);

        ConsumerRecords<String, String> records = KafkaTestUtils.getRecords(
                consumer, Duration.ofSeconds(10));

        assertEquals(1, records.count());
        ConsumerRecord<String, String> record = records.iterator().next();
        assertEquals("order-99", record.key());
        assertEquals("ORDER_CREATED", record.value());
    }
}
```

In this test class, inject `EmbeddedKafkaBroker` and `KafkaTemplate`:

```java
@Autowired
private EmbeddedKafkaBroker embeddedKafka;

@Autowired
private KafkaTemplate<String, String> kafkaTemplate;
```

The test consumer uses a separate group ID so it does not share partitions with the application's listener group. Creating the consumer before sending the record and subscribing to the topic before publishing makes tests more predictable. `try-with-resources` ensures the consumer is closed even if assertions fail.

## 6. Testing a Producer Service with Mockito

A unit test of a service does not need a broker if it only needs to verify that the service calls `KafkaTemplate` with accurate parameters. Example:

```java
@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @InjectMocks
    OrderPublisher orderPublisher;

    @Test
    void publishesOrderCreatedEvent() {
        OrderCreated event = new OrderCreated("order-42");

        orderPublisher.publish(event);

        verify(kafkaTemplate).send(
                "orders", "order-42", event);
    }
}
```

This is a unit test for the service's decision; it does not verify that the broker receives the record, that the serializer works, or that a listener consumes successfully. Do not use mocks to replace all integration tests when the goal is to test the real Kafka flow.

If the service processes the future result, mock the matching `CompletableFuture<SendResult<...>>` and test success/failure branches. In modern Spring Kafka versions, `KafkaTemplate.send()` returns `CompletableFuture`; older projects may use a different future API, so follow the exact dependency version in use.

## 7. Verifying ConsumerRecord Metadata

When testing, do not assert only the payload. `ConsumerRecord` also provides useful details to catch routing or serialization bugs:

| Property | What to Verify |
| --- | --- |
| `topic()` | Record was sent to the right topic |
| `partition()` | Key/partitioner routed the record to the expected partition |
| `offset()` | Record has a valid position in the partition |
| `key()` | Key is accurate to preserve key-based partitioning/ordering |
| `value()` | Deserialized payload has the expected value |
| `headers()` | Correlation ID, event type, trace ID, or business metadata are preserved |
| `timestamp()` | Timestamp has the expected type and time range |

Example checking a header:

```java
Header eventType = received.headers().lastHeader("event-type");
assertNotNull(eventType);
assertEquals(
        "OrderCreated",
        new String(eventType.value(), StandardCharsets.UTF_8));
```

When a header can appear multiple times, use `lastHeader()` or iterate through all headers according to the contract. Do not assume a header is always unique.

## 8. Avoiding Flaky Tests and Resource Leaks

Kafka tests often become unstable when topics, group IDs, or offsets are shared across multiple tests. Principles for repeatable tests:

1. Use dedicated topics and group IDs per test or test class; do not rely on leftover data from previous runs.
2. Create consumers and subscribe before sending records if the test reads directly from a topic.
3. Wait for send futures and listeners using finite timeouts; do not use fixed sleeps.
4. Use `BlockingQueue`, `CountDownLatch`, or Awaitility to synchronize between the test thread and listener threads.
5. Close consumers, producer factories, and listener containers according to Spring/test lifecycles.
6. Avoid running multiple tests concurrently on the same topic/group if tests can consume each other's records.
7. Do not assert absolute offsets if the topic is not clean or contains multiple records.
8. When a test fails, print topic, partition, offset, key, and group ID for easier diagnosis.

When a listener runs asynchronously, wait for the result at a clear synchronization point. A latch counted down inside the listener after processing completes is usually better than only waiting for the producer future to finish.

## 9. Testing DTO Send/Receive and Real Serializers

For DTO payloads, integration tests should use the same serializer/deserializer as the application configuration. For example, producer using `JsonSerializer` and consumer using `JsonDeserializer` with matching trusted packages/type mapping. If tests only use `StringSerializer`, you have not verified the application's JSON configuration.

Cases to test:

- DTOs with null fields or optional fields.
- Enums, timestamps, and numeric types serialize/deserialize accurately.
- Type mapping headers or event types are preserved per contract.
- Invalid payloads produce expected exceptions and error handlers process them properly.
- Old/new schema versions can be read under the compatibility policy if using Schema Registry.

Do not disable validation or widen trusted packages overly just to make tests pass. Configure serializers like the real environment and restrict trusted types according to the application's security model.

## 10. When Is Testcontainers Needed?

Embedded Kafka is convenient, starts fast, and fits basic flow tests. However, if behavior depends on broker version or cluster configuration, use Testcontainers to run the matching Kafka image.

Testcontainers is especially useful when testing:

- Kafka transactions and `read_committed`/`read_uncommitted`.
- EOS V2 and producer fencing with consumer group metadata.
- SASL, TLS, ACLs, and client authentication.
- Broker/client compatibility when upgrading Kafka.
- KRaft, listener addresses, and production-like broker configuration.

Whether using Embedded Kafka or Testcontainers, keep tests independent with dedicated topics/groups and clean up resources after tests finish.

## 11. Common Pitfalls

| Error | Common Cause | Resolution |
| --- | --- | --- |
| `send()` succeeds but listener has not received yet | Producer future only confirms the broker, not listener processing | Wait for a signal from the listener via queue/latch |
| Consumer does not see records | Subscribed after sending, group offset at end, wrong topic, or listener not started | Create consumer first, configure offset appropriately, and wait for container readiness |
| Test reads old records | Reusing topic/group from another test | Separate topics/groups or use a new topic per test |
| Random test timeouts | Using `Thread.sleep()` or timeout too short | Use queue/latch/Awaitility and reasonable timeouts |
| Offset is not 0 | Topic already had records or test ran multiple times | Do not hardcode offsets unless topic state is controlled |
| Listener is not invoked | Wrong `groupId`, `containerFactory`, deserializer, or topic | Check listener container, group, and consumer configuration |
| Test hangs on exit | Consumer/container not closed | Use try-with-resources and Spring lifecycle |

## 12. JUnit Testing Checklist

- [ ] `spring-kafka-test` dependency is compatible with the application's Spring Kafka version.
- [ ] Embedded Kafka creates the right topics and required partition counts.
- [ ] Producer/consumer tests use serializers/deserializers matching the test goal.
- [ ] `KafkaTemplate.send()` results are awaited with a finite timeout.
- [ ] Consumer is verified independently via listener queue/latch or a test consumer.
- [ ] Tests verify topic, key, value, and required metadata.
- [ ] Topic/group IDs do not collide across tests.
- [ ] `Thread.sleep()` is not used to synchronize tests.
- [ ] Consumers and listener containers are closed properly in lifecycle hooks.
- [ ] Transaction, security, or broker-specific features are tested on an appropriate broker when needed.

When testing sending and receiving records in JUnit, verify broker publish acknowledgment and consumer processing completion separately. Embedded Kafka with `KafkaTemplate`, `@KafkaListener`, and `KafkaTestUtils` helps build fast integration tests; Mockito fits service unit tests; and Testcontainers helps verify real broker-dependent behavior. Separating these goals clearly helps tests catch exact bugs in producers, serialization, consumers, and listener containers.
