# Embedded Broker Configuration

An embedded broker allows running a Kafka broker directly inside the test process, enabling tests to send and receive records through a real Kafka broker without starting an external cluster. Spring Kafka provides this support in the `spring-kafka-test` module, primarily through the `@EmbeddedKafka` annotation and the `EmbeddedKafkaBroker` interface.

An embedded broker is suitable for testing producer, consumer, listener container, serialization, partition, and offset flows in an automated environment. It brings tests closer to real Kafka behavior than mocks, though it does not replace testing multi-broker clusters, replication, or production security infrastructure.

## 1. Adding the Testing Dependency

With Maven, add `spring-kafka-test` in the `test` scope. Let Spring Boot dependency management or the Spring Kafka BOM manage the version compatible with the `spring-kafka` version in use:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

With Gradle:

```kotlin
dependencies {
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

If the project uses Spring Boot, you can use the Kafka test starter provided by your Boot version; in all cases, the test dependency must be compatible with the application's Spring Kafka and Kafka client versions. Do not include this test library in the service's runtime artifact.

## 2. Initializing the Broker with @EmbeddedKafka

`@EmbeddedKafka` initializes a broker for the test class and pre-creates topics as declared. Example:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderConsumerIntegrationTest {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    private KafkaTemplate<String, OrderEvent> kafkaTemplate;

    // Tests using the broker and the orders topic.
}
```

Spring Kafka registers `EmbeddedKafkaBroker` in the test context so it can be injected into tests. The `bootstrapServersProperty` attribute maps the embedded broker address to `spring.kafka.bootstrap-servers`, enabling Spring Boot auto-configuration to create producers and consumers connected to the test broker.

Since Spring Kafka 3.0.10, this property is mapped by default to `spring.kafka.bootstrap-servers` when testing with Spring Boot. Declaring it explicitly in the annotation makes the configuration intent clear and maintains compatibility with older versions that support this attribute.

## 3. Configuring Broker Count, Partitions, and Ports

Commonly used attributes of `@EmbeddedKafka` include:

| Attribute | Meaning |
| --- | --- |
| `count` | Number of embedded brokers to start. |
| `partitions` | Default number of partitions for topics created by the annotation. |
| `topics` | List of topics created before tests run. |
| `ports` | Broker ports; use `0` to pick a random port. |
| `brokerProperties` | Broker configuration properties in `key=value` format. |
| `brokerPropertiesLocation` | Resource containing additional broker properties. |

Example creating one broker, two partitions, and a random port:

```java
@EmbeddedKafka(
    count = 1,
    partitions = 2,
    topics = { "orders", "order-events" },
    ports = 0,
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
```

Random ports help avoid conflicts when running multiple test suites on the same machine or in CI. Avoid fixing a port without a clear reason; another process may already occupy that port.

If deeper broker configuration is needed, use `brokerProperties`, for example to adjust `auto.create.topics.enable` or the log directory. Properties depend on the Kafka version; only set values supported by the broker version in use.

## 4. Creating Topics During Testing

Topics declared in `@EmbeddedKafka` are created when the broker starts. If a test needs a topic with specific configuration, it can be created via `EmbeddedKafkaBroker.addTopics(...)`:

```java
@SpringBootTest
@EmbeddedKafka(bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class RetryTopicTest {
    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @BeforeAll
    void createTestTopic() {
        embeddedKafka.addTopics(
            new NewTopic("orders-retry", 3, (short) 1));
    }
}
```

This example creates a retry topic with three partitions and a replication factor of one, suitable for a single broker. By default, `addTopics` throws an exception if topic creation fails, such as when the topic already exists. There is an overload returning a result map so tests can inspect each topic when handling the already-exists case.

Topic names should be separated between tests or test classes so data from an earlier test does not corrupt results of a later test. If reusing a broker across multiple tests, do not assume topics are clean after each method.

## 5. Verifying Spring Boot Connects to the Embedded Broker

In tests using `@SpringBootTest`, `bootstrapServersProperty` must point to the property the application configuration actually reads. Example with default configuration:

```properties
spring.kafka.bootstrap-servers=${spring.embedded.kafka.brokers}
spring.kafka.consumer.group-id=orders-test
spring.kafka.consumer.auto-offset-reset=earliest
```

You can use the `spring.embedded.kafka.brokers` placeholder provided by the embedded broker. However, choose only one way to map bootstrap servers in a test: either set `bootstrapServersProperty` on the annotation or reference the embedded broker property in configuration. Avoid having another configuration override the broker address.

With Spring Kafka 3.0.10 and later, the broker automatically maps the property to `spring.kafka.bootstrap-servers` by default for Spring Boot. If using an older version, declare the mapping explicitly or use the placeholder according to that version's documentation.

## 6. Sending and Receiving Records in Tests

After the broker starts, tests can use the `KafkaTemplate` configured by the application to send records. Use `Future.get` to wait for send acknowledgment and a bounded waiting mechanism to wait for the listener to process:

```java
@Test
void publishesOrderEvent() throws Exception {
    OrderEvent event = new OrderEvent("order-42", "CREATED");

    kafkaTemplate.send("orders", event.orderId(), event)
        .get(10, TimeUnit.SECONDS);

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
        assertThat(orderEventRecorder.events())
            .anyMatch(received -> received.orderId().equals("order-42")));
}
```

`await()` in this example is Awaitility. Waiting on a condition prevents tests from depending on a fixed `Thread.sleep()` duration. If not using Awaitility, you can use a `CountDownLatch` or a synchronized queue with a timeout to receive signals from the listener.

Set `auto-offset-reset=earliest` when a new consumer in a test needs to read records sent before the consumer started. If the listener is already running before the producer and has subscribed successfully, `latest` may also be appropriate; choose based on the test's startup order rather than using one value for every scenario.

## 7. Using KafkaTestUtils with a Test Consumer

`KafkaTestUtils` provides helpers to create consumer properties, read records, and verify results. You can use an independent consumer to verify the broker and serializer without depending on a business listener:

The code below uses `KafkaTemplate<String, String>` to send strings to a test topic:

```java
Map<String, Object> props =
    KafkaTestUtils.consumerProps("orders-test-group", "false", embeddedKafka);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

ConsumerFactory<String, String> consumerFactory =
    new DefaultKafkaConsumerFactory<>(
        props, new StringDeserializer(), new StringDeserializer());

Consumer<String, String> consumer = consumerFactory.createConsumer();
try {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    stringKafkaTemplate.send("orders", "order-42", "created")
        .get(10, TimeUnit.SECONDS);
    ConsumerRecord<String, String> record =
        KafkaTestUtils.getSingleRecord(consumer, "orders");
    assertThat(record.key()).isEqualTo("order-42");
} finally {
    consumer.close();
}
```

Consumers created in tests must be closed in `finally` or try-with-resources if the API/version in use supports it. The `consumeFromAnEmbeddedTopic` helper can seek to the beginning or end offset depending on its parameters; check the right overload so tests do not miss already-sent records.

## 8. Broker Lifecycle and Spring Test Context

An embedded broker has startup overhead, so Spring Kafka recommends reusing one broker across multiple tests when appropriate and separating topics between tests. When using `@EmbeddedKafka` with Spring TestContext, the broker is tied to the application context. With certain `@SpringJUnitConfig` configurations, Spring Kafka documentation recommends `@DirtiesContext` to avoid a race condition during JVM shutdown where the broker closes while the context still needs its resources.

```java
@SpringJUnitConfig
@DirtiesContext
@EmbeddedKafka(topics = "orders")
class OrderMessagingTests {
    // Tests sharing the broker in this context.
}
```

`@DirtiesContext` removes the context from the cache after the test class and can slow down the suite. Only use it when the context/broker lifecycle needs isolation or as recommended for your test configuration; do not add it mechanically to every method.

Spring Kafka 3.0+ also supports a global embedded broker via a JUnit Platform listener, though this feature is disabled by default. Do not mix the global embedded broker with per-test-class `@EmbeddedKafka` in the same suite because they share system properties and can cause unexpected configuration.

## 9. KRaft, ZooKeeper, and Version Compatibility

The embedded broker implementation depends on the Kafka and Spring Kafka versions. With Kafka 4.0, Kafka has moved completely to KRaft; ZooKeeper is no longer supported, and Spring Kafka 4 only keeps the `EmbeddedKafkaKraftBroker` implementation. ZooKeeper-related configuration attributes in the annotation have also been removed.

For projects using older Kafka or Spring Kafka versions, follow the documentation for that exact version because differences in KRaft, ZooKeeper, and broker properties may remain. Generally, prefer `@EmbeddedKafka` so tests do not depend directly on a specific broker implementation.

## 10. When to Use Testcontainers?

An embedded broker runs a Kafka broker in the same test process, which is convenient and fast for integration testing listeners, producers, offsets, retries, or DLTs. However, a single broker does not fully simulate replication, leader election, broker failures, or multi-node cluster configurations.

| Testing Need | Suitable Choice |
| --- | --- |
| Sending/receiving records, listeners, serializers, offsets | Embedded Kafka |
| Retries, DLT, and basic partition routing | Embedded Kafka with explicitly configured topics |
| Specific broker version, multiple brokers, replication | Testcontainers with the appropriate Kafka container |
| TLS/SASL, ACLs, and production-like configuration | Testcontainers or a dedicated integration Kafka environment |
| Failover behavior, broker loss, leader election | Multi-broker test cluster |

Do not use mock brokers to conclude that protocol behavior or broker configuration is correct. Mocks are useful for isolated unit test logic; embedded brokers or container brokers are suitable for integration tests.

## 11. Common Pitfalls

- **Consumer connects to the wrong broker:** check `spring.kafka.bootstrap-servers` and the property mapping of `@EmbeddedKafka`.
- **Test does not receive records:** check topic, group ID, `auto-offset-reset`, listener startup, and serializer/deserializer.
- **Topic already exists:** use per-test topics or handle `addTopics` results intentionally.
- **Port already in use:** use port `0` so the broker picks a random port.
- **Test passes alone, fails in the full suite:** check shared topics, context cache, broker lifecycle, and mixing global/per-class brokers.
- **Broker fails to start on a new version:** verify compatible Kafka/Spring Kafka pair and KRaft/ZooKeeper configuration.

## 12. Embedded Broker Checklist

- Add `spring-kafka-test` in `test` scope and let dependency management manage the version.
- Declare `@EmbeddedKafka` with explicit topics, partitions, and bootstrap property.
- Prefer random ports to avoid CI environment conflicts.
- Use separate topics or a clear data cleanup strategy between tests.
- Wait for send results and listeners using timeouts/conditions instead of arbitrary sleeps.
- Close test-created consumers and resources.
- Choose `@DirtiesContext` or a shared broker according to the test context lifecycle.
- Use Testcontainers or a test cluster when needing to verify replication, security, or failover.

An embedded broker provides a real Kafka broker, initialized automatically within the test lifecycle. Combining `spring-kafka-test`, `@EmbeddedKafka`, accurate bootstrap servers properties, and isolated topics helps keep Spring Kafka producer/consumer tests stable. Choose Testcontainers or a multi-broker cluster when tests need to verify infrastructure characteristics that a single broker cannot simulate.

## References

- [Testing Applications - Spring Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Apache Kafka Support - Spring Boot](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
