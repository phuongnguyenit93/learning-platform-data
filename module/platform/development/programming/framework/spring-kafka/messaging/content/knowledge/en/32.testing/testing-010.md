# Testing @KafkaListener

`@KafkaListener` runs inside a listener container and consumes records asynchronously. Therefore, testing a listener is not merely invoking a Java method and checking the return value. An integration test must confirm that Spring builds the right container, the consumer connects to the right broker/topic, payloads deserialize to the right type, the listener is invoked, business processing completes, and offsets are managed as configured.

Tests should be split into layers. Unit tests check listener logic quickly without Kafka. Integration tests use `@EmbeddedKafka` to verify the listener container and Kafka client inside the same Spring context. Testcontainers fits when needing a broker close to production or testing multiple dependencies together. For all asynchronous tests, wait on a meaningful condition such as `CountDownLatch`, `BlockingQueue`, or Awaitility; never use `Thread.sleep()` to guess when the listener has finished.

## 1. What to Test on a `@KafkaListener`?

A listener has multiple layers of behavior that can fail independently:

| Layer to Verify | Question to Answer | Appropriate Test Approach |
|---|---|---|
| Business logic | Given this event, does the service update data properly? | Unit test calling the method/service directly |
| Spring wiring | Is the listener discovered and registered properly? | Spring context test |
| Consumer configuration | Are topic, group ID, deserializer, and ack mode correct? | Integration test with a broker |
| Serialization | Do producer and consumer share the payload contract? | Send real records and verify the received object |
| Headers/metadata | Are key, partition, offset, timestamp, and headers accurate? | Inspect `ConsumerRecord` or listener parameters |
| Error handling | Do retry, recoverer, and DLT run according to policy? | Integration test with controlled failures |
| Offset/acknowledgment | Are offsets committed after processing per AckMode? | Check committed offsets or redelivery behavior |
| Batch/concurrency | Does batching have the right elements, assignment, and parallel processing? | Multi-partition broker and batch listener |
| Lifecycle | Does the container start/stop and shut down properly? | Inspect registry/container state |

Not every test needs a real broker. Pick the test layer matching the behavior to prove: pure Java logic can be invoked directly; behavior depending on the Kafka client, broker, partitions, or offsets needs a test broker.

## 2. Unit Testing: Calling the Listener Method Directly

Unit tests verify that the listener forwards payloads and metadata to the service properly. These tests do not start a Spring container and do not prove that a consumer can read from Kafka.

Listener:

```java
@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orderCreatedListener",
            topics = "${app.kafka.orders-topic}",
            groupId = "${spring.kafka.consumer.group-id}")
    public void onMessage(ConsumerRecord<String, OrderCreated> record) {
        orderService.handle(
                record.value(),
                record.key(),
                record.partition(),
                record.offset());
    }
}
```

Example payload type:

```java
public record OrderCreated(String eventId, String orderId, long amount) {
}
```

Unit test:

```java
@ExtendWith(MockitoExtension.class)
class OrderCreatedListenerTest {

    @Mock
    private OrderService orderService;

    @InjectMocks
    private OrderCreatedListener listener;

    @Test
    void forwardsPayloadAndKafkaMetadata() {
        OrderCreated event = new OrderCreated("evt-42", "O-42", 120_000);
        ConsumerRecord<String, OrderCreated> record =
                new ConsumerRecord<>("orders", 1, 27L, "O-42", event);

        listener.onMessage(record);

        verify(orderService).handle(event, "O-42", 1, 27L);
    }
}
```

This test is fast and stable. It catches when a listener passes the wrong key, partition, offset, or payload. However, it does not check whether `@KafkaListener` is registered by Spring, whether the broker has the topic, or whether the JSON deserializer works. Those require integration tests.

If the listener takes only a POJO instead of `ConsumerRecord`, the unit test can invoke the method directly with the object. When the listener has `Acknowledgment`, headers, or batch payloads, pass corresponding mocks/fixtures and verify method behavior.

## 3. Adding Testing Dependencies

With Maven, Spring Boot test usually already provides JUnit Jupiter, Mockito, and AssertJ. Add Spring Kafka test utilities in `test` scope:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <scope>test</scope>
</dependency>
```

With Gradle:

```groovy
testImplementation 'org.springframework.kafka:spring-kafka-test'
testImplementation 'org.awaitility:awaitility'
```

Let Spring Boot dependency management or the Spring Kafka BOM select a version compatible with `spring-kafka` in the application. Do not manually add a `spring-kafka-test` version different from the runtime library.

In newer Spring Boot versions, a dedicated Kafka test starter can be used if your version provides `spring-boot-starter-kafka-test`. For Boot 3.x projects, the direct `spring-kafka-test` dependency remains common. Check your project's dependency management before adding a new starter.

## 4. Integration Testing with @EmbeddedKafka

`@EmbeddedKafka` starts a Kafka broker for tests inside the same test process. This is a convenient way to test `@KafkaListener`, `KafkaTemplate`, serialization, topics, partitions, and offsets without a separately installed Kafka server.

Spring Boot test example:

```java
@SpringBootTest(properties = {
        "app.kafka.orders-topic=orders.listener.it",
        "spring.kafka.consumer.group-id=orders-listener-it",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer",
        "spring.kafka.consumer.properties.spring.json.trusted.packages=com.example.orders",
        "spring.kafka.consumer.properties.spring.json.value.default.type=com.example.orders.OrderCreated"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.listener.it",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderCreatedListenerIT {

    @Autowired
    private KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @MockitoBean
    private OrderService orderService;

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderCreatedListener");
        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 1);
    }

    @Test
    void consumesEventAndCallsService() throws Exception {
        OrderCreated event = new OrderCreated("evt-42", "O-42", 120_000);

        kafkaTemplate.send("orders.listener.it", "O-42", event)
                .get(10, TimeUnit.SECONDS);

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
                verify(orderService).handle(
                        eq(event), eq("O-42"), eq(0), anyLong()));
    }
}
```

In this example, `@SpringBootTest` starts the real application context, `@EmbeddedKafka` provides the broker and topic, and `@MockitoBean` replaces `OrderService` with a mock to observe the listener invoking the service. `@MockitoBean` belongs to Spring Framework 6.2+; in older projects, `@MockBean` from Spring Boot test can be used if supported by that version.

`bootstrapServersProperty` maps the embedded broker address to `spring.kafka.bootstrap-servers`. Since Spring Kafka 3.0.10, this property is mapped by default for Spring Boot, though declaring it explicitly makes tests easier to read and keeps compatibility with earlier versions that support this attribute.

`KafkaTemplate.send(...).get(...)` only confirms that the producer received the send result from the broker. It does not prove the listener finished processing. `Awaitility` waits for the service call to occur within a deadline instead of assuming the listener finishes right after `send()` returns.

## 5. Waiting for the Listener to Be Assigned Partitions Before Sending

A test may send a message right after the Spring context starts while the listener container is still joining the group and waiting for partition assignment. If the consumer uses `auto.offset.reset=latest`, messages sent before the consumer begins reading may not be received as the test expects.

You can retrieve the container from `KafkaListenerEndpointRegistry` and wait for assignment:

```java
@Autowired
private KafkaListenerEndpointRegistry registry;

@BeforeEach
void waitForListenerAssignment() {
    MessageListenerContainer container =
            registry.getListenerContainer("orderCreatedListener");
    assertThat(container).isNotNull();
    ContainerTestUtils.waitForAssignment(container, 1);
}
```

`1` is the number of partitions the listener expects to be assigned in this test. If the topic has multiple partitions or container concurrency is greater than one, calculate the actual assigned partition count for the container rather than always passing `1`.

Waiting for assignment eliminates races between the test producer and consumer startup. Additionally, configuring `auto-offset-reset=earliest` lets a new test group read records that existed before its first poll. Choose the offset policy according to the test objective; do not use `earliest` to mask a listener that has not started or lacks assignment.

## 6. Testing Listeners with CountDownLatch or BlockingQueue

Not every test needs Mockito. You can create a test sink to capture records from the listener and wait using a `BlockingQueue`:

```java
@Component
public class CapturingListener {

    private final BlockingQueue<ConsumerRecord<String, String>> received;

    public CapturingListener(
            BlockingQueue<ConsumerRecord<String, String>> received) {
        this.received = received;
    }

    @KafkaListener(topics = "listener.capture.it", groupId = "capture-it")
    public void listen(ConsumerRecord<String, String> record) {
        received.offer(record);
    }
}
```

In test configuration, provide the queue:

```java
@TestConfiguration
class ListenerTestConfiguration {

    @Bean
    BlockingQueue<ConsumerRecord<String, String>> receivedRecords() {
        return new LinkedBlockingQueue<>();
    }
}
```

The test sends a record and retrieves the result:

```java
template.send("listener.capture.it", "key-1", "hello")
        .get(10, TimeUnit.SECONDS);

ConsumerRecord<String, String> received =
        receivedRecords.poll(10, TimeUnit.SECONDS);

assertThat(received).isNotNull();
assertThat(received.key()).isEqualTo("key-1");
assertThat(received.value()).isEqualTo("hello");
```

A queue makes asynchronous results easy to observe. If testing multiple records, use a fresh queue per test or clear the queue before each run so stale records do not cause false passes. Test sinks belong only in fixtures; do not put test queues into production services solely for testing.

## 7. KafkaTestUtils for Creating Consumers and Reading Records

`spring-kafka-test` provides `KafkaTestUtils` to build consumer/producer properties and retrieve records from the embedded broker.

Example reading records independently:

```java
Map<String, Object> props = KafkaTestUtils.consumerProps(
        "orders-verifier", "false", embeddedKafka);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

ConsumerFactory<String, String> consumerFactory =
        new DefaultKafkaConsumerFactory<>(props);

try (Consumer<String, String> consumer = consumerFactory.createConsumer()) {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders.listener.it");

    kafkaTemplate.send("orders.listener.it", "O-42", "payload")
            .get(10, TimeUnit.SECONDS);

    ConsumerRecord<String, String> record =
            KafkaTestUtils.getSingleRecord(consumer, "orders.listener.it");

    assertThat(record.key()).isEqualTo("O-42");
    assertThat(record.value()).isEqualTo("payload");
}
```

Since Spring Kafka 2.5, `consumerProps(...)` sets `auto.offset.reset=earliest` by default so test consumers read records sent before they started. If `latest` behavior is desired, override the property after calling the helper.

`consumeFromAnEmbeddedTopic(...)` seeks assigned partitions to the beginning of the topic by default. There is an overload allowing `seekToEnd`; pick the right option to avoid reading stale records left over from earlier tests. `getSingleRecord(...)` fits when expecting exactly one record; `getRecords(...)` fits when needing to inspect multiple records in a poll.

To avoid cross-talk, use dedicated topics per test or per test class. If reusing topics, explicitly manage offsets, group IDs, and seek positions.

## 8. Checking ConsumerRecord Payload and Metadata

If the listener accepts `ConsumerRecord<K,V>`, you can verify all metadata Kafka delivers to the listener:

```java
assertThat(record.topic()).isEqualTo("orders.listener.it");
assertThat(record.key()).isEqualTo("O-42");
assertThat(record.partition()).isEqualTo(0);
assertThat(record.offset()).isGreaterThanOrEqualTo(0L);
assertThat(record.value().orderId()).isEqualTo("O-42");
assertThat(record.timestamp()).isPositive();
```

If the producer sends business headers:

```java
ProducerRecord<String, OrderCreated> outgoing =
        new ProducerRecord<>("orders.listener.it", "O-42", event);
outgoing.headers().add(
        "trace-id", "trace-123".getBytes(StandardCharsets.UTF_8));
kafkaTemplate.send(outgoing).get(10, TimeUnit.SECONDS);
```

The listener can read the header via `record.headers().lastHeader("trace-id")`. Tests should verify that the header exists, its byte value matches, and missing-header cases are handled. Do not assume every header is a UTF-8 string; numeric headers such as Spring Kafka's partition/offset headers have their own encoding.

## 9. Checking Deserialization and JSON Conversion

A test that only sends a string and receives a string does not verify a JSON deserializer. If production uses `JsonSerializer`/`JsonDeserializer`, send real objects and verify the listener receives the expected type, fields, and values.

JSON consumers normally require configuring trusted packages or matching type mappings:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders
        spring.json.value.default.type: com.example.orders.OrderCreated
```

Tests should cover valid payloads, missing optional fields, null fields, wrong types, and malformed JSON. If using `ErrorHandlingDeserializer`, verify that the listener/error handler receives exception headers or the record routes to the DLT as designed. Deserialization errors happen before the listener is called; do not test them by waiting for a mocked service inside the listener to be invoked.

With Confluent Schema Registry, also test schema ID lookup, compatibility, and registry availability. Embedded Kafka does not provide a Schema Registry; use a registry test container or a separate test Registry environment.

## 10. Testing Retries and DLT

To test retries, produce reproducible failures with short backoffs. Do not rely on random network errors or wait tens of seconds if failures can be simulated with a service mock.

Example of a service failing once then succeeding:

```java
AtomicInteger attempts = new AtomicInteger();

doAnswer(invocation -> {
    if (attempts.incrementAndGet() == 1) {
        throw new TransientOrderException("temporary failure");
    }
    return null;
}).when(orderService).handle(any(), anyString(), anyInt(), anyLong());
```

Send a record and use Awaitility to wait for the service to be called a second time. Verify the invocation count matches the configured retry policy. When using `DefaultErrorHandler`, remember that the retry count is the number of additional attempts after the first processing attempt; total invocations include the initial attempt plus retries.

To test DLT:

1. Declare both the source topic and DLT topic in `@EmbeddedKafka`.
2. Configure `DeadLetterPublishingRecoverer` with `DefaultErrorHandler` and a small retry count.
3. Send a record that causes the listener to fail repeatedly or throw a non-retryable exception.
4. Use a separate consumer group to read from the DLT.
5. Verify key/value, original topic/partition/offset, and exception headers.
6. Verify the source offset is considered recovered only after DLT publishing succeeds per configuration.

Do not merely assert that logs contain an error line. A DLT test must prove the record was actually published to the right topic with sufficient metadata for investigation.

## 11. Testing Batch Listeners

If the listener receives batches, enable batch mode on the container factory and send multiple records to a topic with an appropriate partition count. Tests should verify:

- Listener is invoked with a collection containing the expected elements.
- Record order within each partition is preserved.
- Metadata lists align by index with payloads.
- A batch may contain records from multiple partitions.
- `BatchListenerFailedException` indicates the right index when a record fails.
- Error handler retries/recovers the remaining records properly.

Do not assume a single `send()` produces a single batch listener invocation. Kafka consumer polls group records depending on load, partition assignment, and `max.poll.records`; batch sizes per invocation can vary. To test reliably, send a group of records up front, wait until the consumer receives the full count via latch/queue, and configure the batch listener with suitable timeouts.

## 12. Testing Acknowledgments and Offset Commits

If the listener uses `AckMode.RECORD`, the container commits progress per record after the listener completes successfully. With `AckMode.BATCH`, commits usually occur after the entire poll batch completes successfully. `MANUAL` and `MANUAL_IMMEDIATE` require the listener to call `acknowledge()` at the right time.

Manual acknowledgment tests should prove that records are not acknowledged before the listener calls ack and are committed after ack. You can inspect committed offsets with `AdminClient` or a verifier consumer group, waiting for the commit to complete and distinguishing the processed offset from the next offset to read. Kafka committed offsets normally store the next position, so processing offset 7 successfully usually yields committed offset 8.

With asynchronous listener processing, do not return before the actual work completes if the container commits offsets upon method return. If tasks are handed off to an executor and the listener returns immediately, tests may reveal that offsets advance before side effects complete. When async processing is needed, design appropriate acknowledgment/checkpointing.

## 13. Testing Concurrency and Partition Assignment

To test concurrency, create a topic with multiple partitions and configure a listener container with concurrency greater than one. Retrieve the container from the registry, wait for assignment to complete, and send records with keys to distribute data across partitions.

Things to verify:

- Number of child consumers does not exceed useful partitions in the group.
- Each partition is assigned to at most one consumer in the same group at a time.
- Records with the same key go to the expected partition per the partitioner.
- Listeners can process in parallel across partitions without breaking ordering within the same partition if required by business rules.
- Rebalances do not lose records; duplicate deliveries are handled idempotently.

Do not use a single-partition topic to conclude that concurrency 3 works properly. Only one consumer can receive that partition; the remaining consumers have no partitions to process.

## 14. Testing Listeners with Testcontainers

`@EmbeddedKafka` is convenient for fast tests, though an embedded broker can still differ from production Kafka configurations. Testcontainers runs Kafka in Docker and fits when needing to test broker images/versions, KRaft, networking, or multiple dependencies together.

With Testcontainers 2.x, the Kafka module provides `org.testcontainers.kafka.KafkaContainer` for Apache Kafka images. Example:

Add test dependencies (and manage versions using the project's Testcontainers BOM):

```groovy
testImplementation 'org.testcontainers:testcontainers-kafka'
testImplementation 'org.testcontainers:junit-jupiter'
```

```java
@Testcontainers
@SpringBootTest
class OrderCreatedListenerContainerIT {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers", kafka::getBootstrapServers);
    }

    // Tests sending records and verifying the listener as in the EmbeddedKafka example.
}
```

Choose a Kafka image compatible with the production broker version. Testcontainers requires a Docker-compatible runtime and manages container lifecycles through the JUnit extension. With Testcontainers 2.x, use package `org.testcontainers.kafka.KafkaContainer`; the older class `org.testcontainers.containers.KafkaContainer` is deprecated. If using Confluent Kafka images, select `ConfluentKafkaContainer` accordingly.

Testcontainers fits integration/system tests that run less frequently but offer higher production parity. There is no need to replace all `@EmbeddedKafka` tests with Docker; keep embedded tests fast and add container tests for real-environment-dependent behaviors.

## 15. MockConsumerFactory and MockProducerFactory

The Kafka client provides `MockConsumer` and `MockProducer`. Since Spring Kafka 3.0.7, the framework includes `MockConsumerFactory` and `MockProducerFactory` to integrate these mocks with listener containers and `KafkaTemplate`.

They are useful when testing containers or templates without running a broker. However, mocks do not verify broker protocol, real partition assignment, wire serialization formats, group coordinators, or real transactions.

When testing concurrency, the factory must create a new consumer per call. Do not reuse a single `MockConsumer` instance across multiple child containers. With transactional `MockProducer`, `initTransactions()` must be called before using transactions.

## 16. Avoiding Flaky Tests and Race Conditions

Common reasons Kafka listener tests pass intermittently:

- Sending messages before the listener container has started/received assignment.
- Sharing topics and reading stale records from a previous test.
- Sharing group IDs, causing old offsets to make the test skip records.
- Failing to set an appropriate `auto.offset.reset` when the group has no offsets.
- Using `Thread.sleep()` with durations that are too short or too long.
- Waiting for producer send without waiting for listener processing.
- Running parallel tests on the same topic/group and racing on offsets.
- Failing to close test-created consumers.
- Embedded broker shutting down while the Spring context still uses it.

Remedies:

1. Use dedicated topics and group IDs per test or test class.
2. Wait for listener assignment before sending when tests depend on startup timing.
3. Use `CompletableFuture.get`, `CountDownLatch`, `BlockingQueue`, or Awaitility with finite timeouts.
4. Clear queues/mock state between tests.
5. Close test-created consumers/producers using try-with-resources or lifecycle hooks.
6. Do not run tests sharing the same topic/group in parallel unless data is isolated.
7. Manage embedded broker and Spring context lifecycles; consider `@DirtiesContext` per Spring Kafka recommendations.
8. Do not combine a global embedded broker with per-test-class brokers in the same suite without controlling shared system properties.

## 17. Testing Multiple Classes with One Embedded Broker

Starting a new broker for every test class can slow down the suite. Spring Kafka supports sharing `EmbeddedKafkaBroker` via the Spring test context cache or using a global embedded broker for the entire JUnit test plan.

When using a shared broker:

- Each test should use a dedicated topic or an explicit seek/cleanup strategy.
- Do not share group IDs across independent tests.
- Do not assume topics are empty after the previous test finishes.
- Manage broker shutdown timing relative to the Spring context.
- Do not arbitrarily combine a global embedded broker and per-class `@EmbeddedKafka` because they may share system properties.

For the global embedded broker, configure `spring.kafka.global.embedded.enabled=true` on JUnit Platform and specify broker count, ports, topics, and partitions as needed. This feature suits large suites but requires consistent topic/group isolation conventions.

## 18. Security Testing and Listener Configuration

If production uses SASL/SSL, local embedded broker tests usually run plaintext. Thus they do not prove that credentials, TLS truststores, ACLs, or authorization work properly.

Split testing into:

- Embedded Kafka: listener logic, payloads, headers, retries, DLT, offsets, and partitions.
- Testcontainers or dedicated test broker: listener with production-like Kafka image/version and security configuration.
- Environment smoke tests: verify SASL/SSL, READ/DESCRIBE ACLs, group authorization, and secret injection.

Do not put production secrets into tests. Use test credentials with least privilege and verify that the listener is rejected when required permissions are missing.

## 19. `@KafkaListener` Testing Matrix

| Category | Test Case | Expectation |
|---|---|---|
| Startup | Valid listener ID, existing topic | Container starts and receives partition assignment |
| Delivery | Send a valid record | Listener processes the right payload |
| Serialization | Valid JSON and mismatched type | Deserializes properly or routes error to error handler |
| Metadata | Key, partition, offset, timestamp, headers | Listener receives accurate metadata |
| Group | Two consumers in the same group | Partitions split by assignment, not broadcast to every member |
| Retry | Transient failure then success | Listener is retried according to retry policy |
| DLT | Retries exhausted or non-retryable failure | Record appears on DLT with source metadata |
| Batch | Multiple records in one poll | Payload/header lists align by index |
| Partial batch failure | One record fails at a specific index | Retries/recovers the remaining slice properly |
| Ack | Manual acknowledgment | Offset commits after acknowledgment point |
| Concurrency | Multiple partitions, multiple child consumers | Assignment and parallel processing match design |
| Rebalance | Consumer leaves/joins group | No record loss; duplicates handled idempotently |
| Shutdown | Context closes | Container stops and consumer closes |
| Failure isolation | Broker or downstream temporarily unavailable | Finite test timeout; failures clearly observable |

Not every project needs to implement the entire matrix in every module. Pick the cases matching the listener features actually used and keep representative integration tests for critical paths.

## 20. Troubleshooting Failing Tests

| Symptom | Common Cause | Resolution |
|---|---|---|
| Test times out waiting for listener | Container not started/assigned or wrong topic/group | Check registry ID, topic, group, and `waitForAssignment` |
| Producer send succeeds but mock service is never called | Send ack does not mean listener processed; deserialization may fail | Wait with Awaitility and inspect consumer logs/error handler |
| Test consumer receives no records | Offset reset is `latest`, group already has offsets, or wrong seek | Use a new group, configure `earliest`, check seek position |
| Receives records from previous test | Topic/group shared | Use dedicated topics or explicit seek/cleanup |
| Listener receives `byte[]`/`String` instead of POJO | Wrong deserializer or message converter | Check consumer factory and JSON type mapping |
| No record on DLT | Recoverer not attached to factory, retries not exhausted, or wrong DLT partitions | Check error handler, recoverer, topic, and send result |
| Duplicate invocation | Redelivery, parallel tests, or side effect before commit | Check offsets/acks and make handler idempotent |
| Embedded broker shutdown race | Broker and Spring context lifecycles out of sync | Manage context cleanup and `@DirtiesContext` appropriately |
| Testcontainers fails to start | Docker runtime/image/network unavailable | Check Docker, image tag, and container logs |
| Concurrency test only has one active consumer | Topic has too few partitions | Create enough partitions and wait for assignment |

When a test fails, read listener container, consumer group, and embedded broker logs before increasing timeouts. Longer timeouts cannot fix a wrong group ID, topic, deserializer, or offset reset.

## 21. Workflow for Writing a Stable Integration Test

1. Choose a single behavior to prove, e.g., listener forwards `OrderCreated` to service.
2. Create a dedicated topic and group ID for the test.
3. Start `@EmbeddedKafka` or a Kafka Testcontainer.
4. Configure Spring Boot bootstrap servers, serializer/deserializer, and listener properties.
5. Wait for the container to receive partition assignment if the test depends on startup timing.
6. Send records via `KafkaTemplate` and wait for the send future to complete.
7. Wait for listener side effects via Awaitility, latch, or queue.
8. Assert payload, key, headers, partition, offset, and required side effects.
9. For failure tests, verify retry/DLT/offsets per policy rather than checking logs only.
10. Close self-created resources and ensure broker/context cleanup.

## 22. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Calling the method directly tests `@KafkaListener` | Only tests method logic; does not test container, broker, deserializer, or group |
| `KafkaTemplate.send()` completing means the listener finished | Send future confirms producer/broker result; listener runs asynchronously |
| `Thread.sleep(1000)` is how to wait for a listener | Use latch, queue, Awaitility, or consumer poll with timeout |
| Embedded Kafka is identical to production | Embedded broker is great for integration tests but can differ in image, security, and production topology |
| `auto-offset-reset=earliest` always replays every record | Only applies when the group has no valid committed offset; existing groups resume from committed offsets |
| One partition is enough to test high concurrency | Useful consumers are bounded by assigned partition count |
| `MockConsumer` verifies Kafka protocol | Mocks do not replace a real broker for assignment, networking, transactions, and wire serialization |
| Passing tests prove no duplicates in production | Redelivery/idempotency must be tested and side effects controlled |
| DLT tests only need to verify exceptions are logged | Must read the record from DLT and inspect metadata, key/value, and routing |

## Checklist Before Merging `@KafkaListener` Tests

- Have unit tests for important listener/service logic.
- Have broker-backed integration tests for container/Kafka-dependent behavior.
- Topics and group IDs are isolated between tests.
- Listener assignment is awaited when needed.
- Producer send futures and listener completion are awaited separately.
- `Thread.sleep()` is not used to synchronize tests.
- Serialization/deserialization and headers are verified with real records.
- Retries, DLT, batching, and acknowledgments are tested if used by the application.
- Self-created consumers/producers are closed properly in lifecycle hooks.
- Embedded broker and Spring context have no shutdown races.
- Testcontainers uses compatible images/versions when production parity is needed.
- Timeouts are finite and logs provide enough detail for failure diagnosis.
- Tests prove idempotency or redelivery behavior if the listener produces side effects.

Testing `@KafkaListener` requires combining unit tests for logic and integration tests for container/broker behavior. `@EmbeddedKafka` with `KafkaTestUtils` enables fast Kafka flow verification in the test suite; Testcontainers increases parity with production brokers and dependencies. By isolating topics/groups, waiting for assignment, awaiting listeners via asynchronous signals, and verifying retry/offset/DLT contracts, tests remain stable and accurately reflect how listeners operate.

## References

- [Spring for Apache Kafka – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot – Apache Kafka Support and Testing with Embedded Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Testcontainers for Java – Kafka Module](https://java.testcontainers.org/modules/kafka/)
- [Testcontainers for Java – General Docker Environment Requirements](https://java.testcontainers.org/supported_docker_environment/)
