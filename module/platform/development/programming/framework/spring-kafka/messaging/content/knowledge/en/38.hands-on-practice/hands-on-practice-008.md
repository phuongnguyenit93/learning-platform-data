# Adding Tests with an Embedded Broker

When developing a Spring Kafka application, you need to test producers, consumers, and listener containers against a real Kafka broker. `spring-kafka-test` provides `@EmbeddedKafka` to start an embedded broker right inside the test process. As a result, integration tests can send records via `KafkaTemplate`, have `@KafkaListener` receive records, and verify payloads, keys, headers, partitions, and processing outcomes.

An embedded broker lets you test Kafka flows without installing a separate cluster or depending on Docker. It is not a mock of `KafkaTemplate`: producers and consumers still use the real Kafka client and Kafka protocol to communicate with the broker. However, embedded broker setups are typically smaller than production; behaviors depending on multiple brokers, replication, TLS/SASL, or production topologies require additional testing in an appropriate environment.

## 1. Why Use an Embedded Broker?

Unit tests can test business services with Mockito, but do not prove that serializers, deserializers, topics, partitions, consumer groups, and listener containers work together properly.

Embedded Kafka is well suited for testing:

- Producers sending records via `KafkaTemplate` and receiving acknowledgments.
- Consumers receiving records from topics using the Kafka client.
- `@KafkaListener` registration and invocation.
- Accurate propagation of key, value, headers, timestamp, and partition metadata.
- Consumer groups and offsets behaving as configured.
- Retries, error handlers, and dead-letter topics in a test broker.
- Transactions and `read_committed` when the test broker is configured to support them.

Basic testing flow:

```text
JUnit test
    |
    | KafkaTemplate.send(...)
    v
Embedded Kafka broker
    |
    | topic / partition
    v
Spring Kafka listener container
    |
    v
@KafkaListener
    |
    v
Test probe (BlockingQueue)
    |
    v
JUnit assertions
```

The test sends a record to a real broker and then waits for the listener to process it asynchronously. Therefore, avoid using a fixed `Thread.sleep()` to guess when the listener has finished.

## 2. Adding the spring-kafka-test Dependency

With Maven, add the dependency in `test` scope:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

If the project uses Spring Boot dependency management, let the BOM manage a version compatible with the active Spring Kafka version. Avoid choosing a `spring-kafka-test` version that differs from the application's `spring-kafka` version.

With Gradle:

```kotlin
testImplementation("org.springframework.kafka:spring-kafka-test")
```

If the project does not use Spring Boot dependency management, declare a version matching the Spring Kafka runtime. `spring-kafka-test` provides `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `KafkaTestUtils`, and `ContainerTestUtils` to support tests.

## 3. Starting the Broker with @EmbeddedKafka

Place `@EmbeddedKafka` on the test class to start the broker for the test context lifecycle:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderMessagingIntegrationTest {
}
```

Notable attributes:

| Attribute | Meaning |
| --- | --- |
| `partitions` | Number of partitions created for each declared topic |
| `topics` | List of topics to create before the test runs |
| `bootstrapServersProperty` | Spring property receiving the embedded broker's bootstrap address |
| `brokerProperties` | Additional broker properties for the test environment |
| `kraft` | Selects KRaft mode in Spring Kafka versions supporting this attribute |

Using `bootstrapServersProperty = "spring.kafka.bootstrap-servers"` connects Spring Boot's `ProducerFactory` and `ConsumerFactory` to the embedded broker. If using a custom property, ensure both producer and consumer read from that exact property.

## 4. Configuring Spring Boot for Testing

In integration tests, the application should use the embedded broker's bootstrap servers and a dedicated test consumer group:

```java
@SpringBootTest(properties = {
        "spring.kafka.consumer.group-id=orders-embedded-test",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderMessagingIntegrationTest {
}
```

`auto-offset-reset=earliest` lets a fresh test consumer group read from the start of the partition when it has no committed offset yet. `enable-auto-commit=false` aligns with Spring Kafka listener containers, which manage offsets according to `AckMode`.

If a listener declares `groupId` directly on `@KafkaListener`, that value may override the default group ID. Ensure tests use a dedicated group so they do not read committed offsets left over from a previous test run.

## 5. Creating a Listener Probe to Observe Records

A straightforward way to inspect listener deliveries is pushing received records into a `BlockingQueue`. Tests can poll records from the queue with a timeout instead of waiting with `sleep`.

```java
import java.util.concurrent.BlockingQueue;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

public class TestOrderListener {

    private final BlockingQueue<ConsumerRecord<String, String>> received;

    public TestOrderListener(
            BlockingQueue<ConsumerRecord<String, String>> received) {
        this.received = received;
    }

    @KafkaListener(
            id = "embedded-orders-listener",
            topics = "orders.created",
            groupId = "orders-embedded-test")
    public void listen(ConsumerRecord<String, String> record) {
        received.add(record);
    }
}
```

In a real application, the listener normally calls an application service or repository. The probe above is strictly for testing, capturing records so assertions can inspect the key, value, headers, topic, partition, and offset.

## 6. Registering the Probe in the Spring Test Context

You can declare a nested `@TestConfiguration` to create the queue and test-only listener bean:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
static class ListenerTestConfiguration {

    @Bean
    BlockingQueue<ConsumerRecord<String, String>> receivedRecords() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    TestOrderListener testOrderListener(
            BlockingQueue<ConsumerRecord<String, String>> receivedRecords) {
        return new TestOrderListener(receivedRecords);
    }
}
```

Import this configuration into the test class:

```java
@Import(ListenerTestConfiguration.class)
```

Spring Kafka detects `@KafkaListener` on the listener bean and registers the endpoint in the listener container registry. The test can retrieve the container by ID to wait for partition assignment before sending records.

If the application already has a real listener, you can verify side effects on the application service/repository instead of creating a separate probe. Avoid letting both the production listener and a probe consume the same topic in the same group when testing a specific consumer; they will split partitions and may receive different records.

## 7. Waiting for Listener Partition Assignment

Containers start asynchronously. Right after the Spring context is created, the consumer may not have finished joining the group and receiving its partition assignment. Use `ContainerTestUtils.waitForAssignment(...)` to wait for this state:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@Autowired
KafkaListenerEndpointRegistry registry;

@BeforeEach
void waitForListenerAssignment() {
    var container = registry.getListenerContainer("embedded-orders-listener");
    assertThat(container).isNotNull();
    ContainerTestUtils.waitForAssignment(container, 1);
}
```

The argument `1` is the total number of partitions the listener is expected to be assigned in this single-partition topic example. If the listener subscribes to multiple topics or a multi-partition topic, calculate the expected total partitions for the test's assignment.

Waiting for assignment reduces race conditions: the test does not send records before the consumer is ready. It does not replace a timeout when waiting for the listener to finish processing a record.

## 8. Sending Records with KafkaTemplate and Verifying Results

Tests can inject `KafkaTemplate` just like the production application:

```java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.SendResult;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;

@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Autowired
BlockingQueue<ConsumerRecord<String, String>> receivedRecords;

@Test
void sendsRecordAndListenerReceivesIt() throws Exception {
    SendResult<String, String> result = kafkaTemplate
            .send("orders.created", "order-42", "created")
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
            .isEqualTo("orders.created");

    ConsumerRecord<String, String> received =
            receivedRecords.poll(10, TimeUnit.SECONDS);

    assertThat(received).isNotNull();
    assertThat(received.key()).isEqualTo("order-42");
    assertThat(received.value()).isEqualTo("created");
    assertThat(received.topic()).isEqualTo("orders.created");
}
```

`send(...).get(...)` waits for the producer to receive a send result from the broker. It does not wait for the listener to finish processing; therefore the test polls the queue with its own timeout.

If `send()` fails, `get()` throws an exception (typically wrapped in `ExecutionException`). Tests should let this error fail the test or assert the specific cause in failure-scenario tests.

## 9. Verifying Kafka Headers

The embedded broker stores headers alongside records, so tests can verify correlation IDs or other metadata:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

@Test
void preservesCorrelationIdHeader() throws Exception {
    ProducerRecord<String, String> record = new ProducerRecord<>(
            "orders.created", "order-43", "created");

    record.headers().add(new RecordHeader(
            "correlation-id",
            "corr-test-43".getBytes(StandardCharsets.UTF_8)));

    kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

    ConsumerRecord<String, String> received =
            receivedRecords.poll(10, TimeUnit.SECONDS);

    assertThat(received).isNotNull();
    var header = received.headers().lastHeader("correlation-id");
    assertThat(header).isNotNull();
    assertThat(new String(header.value(), StandardCharsets.UTF_8))
            .isEqualTo("corr-test-43");
}
```

Kafka header values are byte arrays. Tests should check encoding the same way the real producer and consumer do, rather than comparing directly against a `String`.

## 10. Verifying Partitions and Metadata

With a single-partition topic, records are normally written to partition `0`. You can check the metadata returned by the broker:

```java
assertThat(result.getRecordMetadata().partition()).isEqualTo(0);
assertThat(result.getRecordMetadata().offset()).isGreaterThanOrEqualTo(0);
```

If a topic has multiple partitions, do not hardcode a partition when the producer uses the default partitioner and a key. Instead, verify the partition lies within the valid range or verify that records with the same key land on the same partition when testing key ordering.

To verify listener partition assignment, use `ContainerTestUtils.waitForAssignment()` and inspect record metadata received by the listener. Topic partition count, concurrency, and number of consumers in the group together determine parallelism.

## 11. Using KafkaTestUtils to Create an Independent Test Consumer

Sometimes you need to inspect records in a topic without going through `@KafkaListener`. `KafkaTestUtils` helps build consumer properties for the embedded broker:

```java
import java.time.Duration;
import java.util.Map;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Autowired
EmbeddedKafkaBroker embeddedKafkaBroker;

@Test
void readsRecordWithTestConsumer() {
    Map<String, Object> props = KafkaTestUtils.consumerProps(
            "orders-read-test", "false", embeddedKafkaBroker);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);

    try (Consumer<String, String> consumer = new KafkaConsumer<>(props)) {
        embeddedKafkaBroker.consumeFromAnEmbeddedTopic(
                consumer, "orders.created");

        kafkaTemplate.send("orders.created", "order-44", "paid");

        var records = KafkaTestUtils.getRecords(
                consumer, Duration.ofSeconds(10));

        assertThat(records.count()).isGreaterThan(0);
        assertThat(records.iterator().next().value()).isEqualTo("paid");
    }
}
```

The test consumer uses a separate group ID and is closed via try-with-resources. `consumeFromAnEmbeddedTopic()` sets up subscription/assignment for the embedded topic; `KafkaTestUtils.getRecords()` polls records with a timeout. If a test needs to assert a specific record in a topic that already contains earlier records, use a dedicated topic or filter by key/value instead of assuming the first record returned is the one just sent.

## 12. Testing Deserialization and Message Conversion

If the producer sends JSON or objects, the embedded broker test configuration must use the same serializers/deserializers or converters as the application.

Points to check:

- JSON fields serialize with the expected names and types.
- The consumer deserializes into the expected DTO/record.
- Header mapping does not drop custom headers.
- Nulls, optional fields, and timestamps have consistent semantics.
- Malformed payloads pass through `ErrorHandlingDeserializer`/error handler according to policy.
- Type headers or trusted packages are configured properly when using JSON type mapping.

A test where both producer and consumer use `StringSerializer` only proves string transport. If production uses Avro, Protobuf, or JSON serializers, write integration tests with the actual serializers and matching schema fixtures.

## 13. Testing Listeners Calling Application Services

If you want to test the application's real listener, you can replace or spy on the application service in the Spring test context and verify it receives the event after the record passes through the broker.

In Spring Boot versions supporting `@MockitoBean`, you can mock the service:

```java
@MockitoBean
OrderProjectionService orderProjectionService;

@Test
void listenerDelegatesToApplicationService() throws Exception {
    kafkaTemplate.send("orders.created", "order-45", "created")
            .get(10, TimeUnit.SECONDS);

    await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
            verify(orderProjectionService).process("order-45", "created"));
}
```

This example uses a hypothetical service method `process(String key, String value)`. If an older Spring Boot version lacks `@MockitoBean`, use the mock-bean annotation supported by that version. While mocking the service verifies listener invocation, additional tests are still needed for the real business logic.

## 14. Testing Multiple Partitions and Concurrency

To test listener concurrency, create a topic with multiple partitions:

```java
@EmbeddedKafka(
        partitions = 3,
        topics = "orders.concurrent",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
```

The listener can be configured as:

```java
@KafkaListener(
        id = "concurrent-orders-listener",
        topics = "orders.concurrent",
        groupId = "orders-concurrent-test",
        concurrency = "3")
public void listen(String payload) {
    // Process the record.
}
```

With three partitions and concurrency three, the container can run up to three consumers in the group, each assigned partitions by the assignor. Do not assert that each thread will always receive one exact partition in a fixed order; assignment depends on the group coordinator and partition assignor.

Tests should verify that all records are processed, without assuming global ordering across multiple partitions. Ordering is only guaranteed within a single partition.

## 15. Testing Offsets and Consumer Groups

An embedded broker enables inspecting consumer groups and committed offsets via `AdminClient` or separate test consumer groups.

Useful scenarios:

- Listener succeeds and offsets advance according to `AckMode`.
- Listener throws an exception and the record is retried/redelivered.
- Manual acknowledgment commits only after calling `acknowledge()`.
- Consumer restarts and resumes from the committed offset.
- Two different group IDs read the same topic independently.
- Two consumers in the same group split partitions.

Do not share the same group ID across unrelated tests. Committed offsets from an earlier run can prevent a new test from reading records. Use separate group IDs, separate topics, or reset data under an explicit strategy.

## 16. Testing Retry and Dead Letter Topics

You can declare the main topic and DLT directly on the annotation:

```java
@RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 100),
        dltTopicSuffix = ".dlt")
@KafkaListener(topics = "orders.retry", groupId = "orders-retry-test")
public void listen(String payload) {
    orderService.process(payload);
}
```

With Embedded Kafka, pre-create the required retry topics and DLT or configure topic creation to match the test setup. Send a record that causes the listener to fail, then consume the DLT and verify the payload/header metadata.

Tests need to wait asynchronously with a timeout sufficient for retry delays and poll cycles. Do not assert exact retry timestamps because scheduling and broker polling can cause processing to happen later than the minimum backoff interval.

Non-blocking retry via `@RetryableTopic` does not combine with container transactions and does not support batch listeners. If the application uses a transactional listener, test retry/rollback via `AfterRollbackProcessor` rather than an incompatible retry-topic configuration.

## 17. Testing Transactions with an Embedded Broker

If you need to test Kafka transactions, the embedded broker must be configured with appropriate transaction state topic settings. For a single-node broker in tests:

```java
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.input", "orders.output"},
        brokerProperties = {
                "transaction.state.log.replication.factor=1",
                "transaction.state.log.min.isr=1"
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
```

Transactional producers require a unique `transactionIdPrefix`. Consumers use `isolation.level=read_committed` to see only committed outputs. Tests should cover both commits and aborts, and verify input offsets when using transactional listeners.

A replication factor of 1 is only for a single-node embedded broker; it does not reflect production durability. When testing broker configs, TLS/SASL, or multi-broker behavior, consider Testcontainers or an appropriate integration environment.

## 18. Isolating Tests and Avoiding Flakiness

Kafka tests can interfere with each other through shared topics, group IDs, offsets, and leftover records. Apply these principles:

- Use dedicated topics or ensure each test uses distinct data/keys.
- Use a dedicated consumer group ID per test class or run.
- Declare an explicit partition count in `@EmbeddedKafka`.
- Wait for listener assignment with `ContainerTestUtils.waitForAssignment()`.
- Use `BlockingQueue`, `CountDownLatch`, or Awaitility to wait for the listener.
- Set bounded timeouts on producer futures and consumer polls.
- Never rely on fixed `Thread.sleep()`.
- Clear queues/repositories before each test.
- Close manually created consumers with try-with-resources.
- Do not run tests sharing the same topic/group in parallel unless isolated.

If a test fails only on CI, check consumer assignments, rebalance logs, timeouts, topic/group reuse, and CPU load rather than arbitrarily bumping timeouts.

## 19. How Do Embedded Kafka and Testcontainers Differ?

| Criterion | Embedded Kafka | Testcontainers Kafka |
| --- | --- | --- |
| Execution | Embedded broker inside the test process | Broker running inside a container |
| Docker | Not required | Requires Docker runtime |
| Speed | Usually fast for integration tests | Usually slower due to container startup |
| Broker version | Follows Spring Kafka test dependency | Can pick a specific image/version |
| Production-like config | Suitable for basic Kafka behaviors | More flexible for broker configs, security, and topology |
| Best suited for | Producer/listener, headers, offsets, basic retry | Compatibility, TLS/SASL, broker images, and production-like setups |

Embedded Kafka does not replace all infrastructure tests. For instance, a single embedded broker cannot demonstrate replication, leader failover, or behavior when a node drops in a multi-broker cluster.

## 20. Troubleshooting When Testing with Embedded Kafka

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Spring context connects to wrong broker | `bootstrapServersProperty` does not match the Spring property used | Align producer/consumer properties with the embedded broker |
| Listener receives no records | Container has not assigned partitions yet or wrong topic/group | Wait for assignment, check listener ID/topic/group |
| Producer future times out | Broker not ready yet or test uses wrong bootstrap | Wait for broker startup, inspect send exception and metadata |
| Test reads old records | Topic/group reused | Use dedicated topics/groups or filter by event ID |
| Test is flaky due to sleep | Listener runs asynchronously | Use queue/latch/Awaitility with a timeout |
| `NoSuchBeanDefinition` for KafkaTemplate | Context does not auto-configure producer or test config lacks bean | Check dependencies and Spring Boot Kafka auto-configuration |
| Transaction test fails to run | Broker lacks transaction state settings | Configure appropriate replication factor and min ISR |
| Multiple listeners receive/miss expected records | Listeners share the same consumer group | Use group IDs matching the test goal |
| Port/property conflicts across test contexts | Multiple embedded brokers or shared system properties | Use isolated bootstrap properties, isolate contexts and lifecycle |

## 21. Integration Test Completion Checklist

- [ ] `spring-kafka-test` dependency present with compatible version.
- [ ] `@EmbeddedKafka` declares topics and partitions explicitly.
- [ ] Spring producer/consumer use the embedded broker's bootstrap property.
- [ ] Consumer group ID is dedicated to the test.
- [ ] Listener container waits for assignment before sending records.
- [ ] Producer future is awaited with a timeout.
- [ ] Listener synchronization uses queue/latch/Awaitility.
- [ ] Assertions verify key, value, topic, partition, and headers where needed.
- [ ] Serializers/deserializers match the application configuration under test.
- [ ] Retry/DLT/transactions have dedicated tests matching real semantics.
- [ ] Tests do not depend on execution order or leftover offsets from prior runs.
- [ ] Test consumers and resources are closed/cleaned up.
- [ ] Production concerns like replication, security, and failover have separate infrastructure tests.

## 22. Conclusion

`@EmbeddedKafka` and `spring-kafka-test` make it possible to add integration tests backed by a real broker for Spring Kafka applications without standing up a separate cluster. Declare topics/partitions on the annotation, point Spring Boot to the embedded broker's bootstrap servers, wait for listener assignment, and then send records with `KafkaTemplate`. Use futures to confirm producer sends and `BlockingQueue`, latches, or Awaitility to wait for listener processing.

Verify both payloads and metadata such as key, partition, offset, and headers; use dedicated consumer groups to prevent cross-test interference. Embedded Kafka is suitable for most producer/consumer/listener, retry, and basic transaction tests. For multi-broker setups, replication, security, or specific production broker configurations, supplement with Testcontainers or an appropriate integration environment. That way, the test suite validates both business behavior and messaging boundaries without becoming dependent on random timing.

## References

- [Spring for Apache Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Embedded Kafka Broker](https://docs.spring.io/spring-kafka/reference/testing.html#embedded-kafka)
- [Spring for Apache Kafka — KafkaTestUtils API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring for Apache Kafka — ContainerTestUtils API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/ContainerTestUtils.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
