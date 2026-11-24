# Testing KafkaTemplate

**KafkaTemplate** is the Spring Kafka component producers use to send records to Kafka. A meaningful test needs to verify more than just that the `send` method was called: whether the record serializes properly, the broker receives it, metadata is valid, and a consumer can read the payload back. For error branches, tests must prove the application observes exceptions and does not silently treat a failed send as a success.

In the **SPRING_KAFKA_MESSAGING** module, KafkaTemplate is part of the event send/receive flow alongside @KafkaListener, topics, partitions, offsets, and consumer groups. This lesson focuses on testing producers across multiple levels—from unit tests for event-publishing logic to integration tests with a real broker—while also verifying callbacks, serialization, connection failures, and test isolation.

## Expected outcomes

After this lesson, you will be able to:

- Distinguish unit tests, slice/configuration tests, and integration tests for producers.
- Use Mockito to verify how a service calls KafkaTemplate and forwards results.
- Use EmbeddedKafka to verify records are actually written and readable.
- Verify topic, key, value, partition, offset, and headers.
- Verify serialization/deserialization of event payloads.
- Test `CompletableFuture`, success callbacks, and failure callbacks.
- Write deterministic tests for timeouts, broker failures, and serialization errors.
- Use Testcontainers when you need a broker close to the deployment environment.
- Isolate topics, consumer groups, and test data to avoid execution-order dependencies.
- Define clearly the limits of a broker-acknowledged send.

## 1. What needs to be tested on KafkaTemplate?

A producer typically has multiple responsibilities: accepting business data, building an event, choosing topic and key, sending the record, and handling the send result. Not every responsibility requires a broker to test.

Divide test objectives by boundary:

| Objective | Suitable test level | What to verify |
|---|---|---|
| Build event from business data | Unit test | Event has expected `eventId`, timestamp, and contents. |
| Choose topic and key | Unit test | Service calls KafkaTemplate with the right topic, key, and value. |
| Handle future | Unit test | Result or exception is forwarded properly. |
| Serializer configuration | Integration test | Objects serialize to bytes and decode accurately. |
| Write record to Kafka | Integration test | Broker acknowledges record and returns metadata. |
| Read record back | Integration test | Topic, key, value, and headers match expectations. |
| Partition distribution | Integration test with multi-partition topic | Keys route according to partitioner configuration. |
| Fault tolerance | Integration/failure test | Application reacts appropriately when broker or connection fails. |

A unit test only proves service logic against mocked dependencies. It does not prove a broker is running, serializers are compatible, or metadata discovery works. Conversely, integration tests do not need to repeat every pure logic branch already covered by unit tests.

## 2. Unit testing services that use KafkaTemplate

Unit tests are well suited for verifying that a service calls KafkaTemplate with the expected arguments and returns the future to its caller. Use Mockito to mock KafkaTemplate so tests run without starting a broker.

Example service:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

Example unit test verifying the call and returned future:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderEventPublisherTest {

    @Mock
    KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    private OrderEventPublisher publisher;

    @BeforeEach
    void setUp() {
        publisher = new OrderEventPublisher(kafkaTemplate);
    }

    @Test
    void shouldSendEventWithOrderIdAsKey() {
        OrderCreatedEvent event = new OrderCreatedEvent(
                "evt-1001",
                "order-1001",
                Instant.parse("2026-01-10T10:15:30Z"),
                new BigDecimal("125.50")
        );

        CompletableFuture<SendResult<String, OrderCreatedEvent>> expected =
                new CompletableFuture<>();

        when(kafkaTemplate.send(
                "orders.created",
                "order-1001",
                event
        )).thenReturn(expected);

        CompletableFuture<SendResult<String, OrderCreatedEvent>> actual =
                publisher.publish(event);

        assertThat(actual).isSameAs(expected);
        verify(kafkaTemplate).send(
                "orders.created",
                "order-1001",
                event
        );
        verifyNoMoreInteractions(kafkaTemplate);
    }
}
~~~

This test verifies three things: the topic is `orders.created`, the key is `orderId`, and the publisher returns the future from KafkaTemplate. It does not verify that a broker wrote the record.

If the service includes event-construction logic, verify the event before sending. For example, when receiving an `Order`, a publisher builds an `OrderCreatedEvent` with a unique `eventId`, timestamp, and total; unit tests can assert those fields without Kafka.

Avoid mocking deep internal Kafka producer classes. Keep unit tests focused on the service's contract with KafkaTemplate.

## 3. Testing failed futures with unit tests

`KafkaTemplate.send` returns a future. When the producer cannot complete sending, the future can complete exceptionally. You can create a failed future to verify the service preserves the error state and does not turn it into a fake success.

Example:

~~~java
@Test
void shouldPropagateSendFailure() {
    OrderCreatedEvent event = new OrderCreatedEvent(
            "evt-1002",
            "order-1002",
            Instant.parse("2026-01-10T10:15:30Z"),
            new BigDecimal("80.00")
    );

    CompletableFuture<SendResult<String, OrderCreatedEvent>> failed =
            new CompletableFuture<>();

    failed.completeExceptionally(
            new KafkaException("Broker is unavailable")
    );

    when(kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
    )).thenReturn(failed);

    CompletableFuture<SendResult<String, OrderCreatedEvent>> actual =
            publisher.publish(event);

    assertThat(actual).isCompletedExceptionally();
}
~~~

If the publisher attaches `whenComplete` to log or update metrics, the returned future should still reflect the failure if the callback only observes the result. Tests can complete the future exceptionally and verify that callbacks or error-handling collaborators are invoked.

When asserting specific exceptions, keep in mind `CompletableFuture.join` typically wraps errors in `CompletionException`, while `get` wraps them in `ExecutionException`. Assert on the root cause rather than relying on the wrapper class.

Failure unit tests are valuable for scenarios difficult to reproduce reliably with a real broker, such as callbacks receiving exceptions, retry policies invoking the expected number of attempts, or publishers delegating errors to a dedicated handler.

## 4. Integration testing with EmbeddedKafka

**EmbeddedKafka** provides an embedded broker for Spring Kafka testing. It works well for fast integration tests, verifying that KafkaTemplate sends real records and a consumer can read them within the same test context.

A test class can declare topics and bind the embedded broker address into Spring Boot configuration:

~~~java
@SpringBootTest(properties = {
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.acks=all"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaTemplateIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

}
~~~

The serializer properties in this example use `String` to focus on send behavior. If the application sends DTOs, use the actual `JsonSerializer`/`JsonDeserializer` or project serializers. Your Spring Kafka version must support the `@EmbeddedKafka` and `bootstrapServersProperty` declaration syntax.

Example verifying the sent record (place this method inside the class above, replacing the placeholder body):

~~~java
@Test
void shouldPublishRecordAndReadItBack() throws Exception {
    String topic = "orders.created";
    String groupId = "orders-template-test";

    Map<String, Object> consumerProps =
            KafkaTestUtils.consumerProps(
                    groupId,
                    "false",
                    embeddedKafka
            );

    consumerProps.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
    );

    try (Consumer<String, String> consumer =
                 new DefaultKafkaConsumerFactory<>(
                         consumerProps,
                         new StringDeserializer(),
                         new StringDeserializer()
                 ).createConsumer()) {

        embeddedKafka.consumeFromAnEmbeddedTopic(consumer, topic);

        SendResult<String, String> result =
                kafkaTemplate.send(
                        topic,
                        "order-1001",
                        "{\"orderId\":\"order-1001\",\"status\":\"CREATED\"}"
                ).get(10, TimeUnit.SECONDS);

        RecordMetadata metadata = result.getRecordMetadata();

        assertThat(metadata.topic()).isEqualTo(topic);
        assertThat(metadata.partition()).isEqualTo(0);
        assertThat(metadata.offset()).isGreaterThanOrEqualTo(0);

        ConsumerRecord<String, String> record =
                KafkaTestUtils.getSingleRecord(
                        consumer,
                        topic,
                        Duration.ofSeconds(10)
                );

        assertThat(record.key()).isEqualTo("order-1001");
        assertThat(record.value())
                .contains("\"status\":\"CREATED\"");

        assertThat(record.partition()).isEqualTo(metadata.partition());
        assertThat(record.offset()).isEqualTo(metadata.offset());
    }
}
~~~

This test creates the consumer before sending the record, then sends with KafkaTemplate, waits for the future within a timeout, and reads a single record back from the topic. Comparing partition and offset confirms the read record is the exact one the producer just sent.

Classes `KafkaTestUtils`, `EmbeddedKafkaBroker`, `DefaultKafkaConsumerFactory`, and `ConsumerRecord` must be imported from Spring Kafka or Apache Kafka respectively. Helper APIs can vary across versions; match the Spring Kafka version managed by your project.

Using `get` in integration tests is appropriate because the test must wait for the outcome to assert on it. In production code, avoid blocking threads merely to wait for a send to complete when futures or callbacks can be used.

## 5. Checking topic, key, partition, and offset

A producer test should verify attributes that affect consumer behavior.

- **Topic:** the record was sent to the right event stream.
- **Key:** the record carries the intended business key, such as `orderId`.
- **Partition:** the record is routed according to the partitioner and topic configuration.
- **Offset:** the broker assigned the record's position in the partition.
- **Timestamp:** the timestamp is set and returned according to producer/broker timestamp settings.
- **Headers:** extra metadata such as `correlation-id` or `event-type` is preserved.

Example sending a record with a header:

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.created",
                null,
                System.currentTimeMillis(),
                "order-1001",
                "{\"orderId\":\"order-1001\"}"
        );

record.headers().add(
        "correlation-id",
        "corr-1001".getBytes(StandardCharsets.UTF_8)
);

SendResult<String, String> result =
        kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

assertThat(result.getProducerRecord().headers()
        .lastHeader("correlation-id")).isNotNull();
~~~

To verify headers on the broker side, read back the `ConsumerRecord` and assert headers on the received record. Checking `ProducerRecord` before sending only confirms the producer's input object contained the header; it does not prove the record was written and read back intact.

When checking partitions, do not assume a given key always lands on a fixed partition number unless partition count, partitioner, and settings are explicitly pinned. Instead, assert that the record has the right key and metadata partition matches expected behavior in the test setup.

## 6. Testing serialization and event contracts

Kafka stores bytes; the producer serializer converts objects to bytes and the consumer deserializer converts bytes back to objects. Therefore, testing with `StringSerializer` is insufficient to validate your application's JSON or Avro/Protobuf configuration.

For JSON, include at least two kinds of tests:

1. **Serialization test:** objects serialize into valid payloads containing the required fields and data types.
2. **Round-trip integration test:** send an object with KafkaTemplate, then read the record using a consumer with the real deserializer to verify the reconstructed object.

Example DTO:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
~~~

When testing JSON, pay attention to:

- Required fields are present and not renamed unexpectedly.
- `Instant` and `BigDecimal` serialize in a consistent format.
- New fields can be handled by older consumers per compatibility rules.
- Type headers are handled properly if the application uses Spring Kafka type metadata.
- Trusted packages are restricted appropriately to permitted models for deserialization.
- Malformed payloads or missing required fields produce observable, handleable errors.

Do not merely assert that the payload contains a substring. When the event contract matters, deserialize back to the DTO and compare fields. This catches type mismatches, null values, and schema changes that simple string checks miss.

For Avro or Protobuf, tests must use the real schema and serializer/deserializer, and verify compatibility between supported producer and consumer versions.

## 7. Testing callbacks and asynchronous results

In Spring Kafka 3.x, `KafkaTemplate.send` returns `CompletableFuture`. Tests can await future completion to inspect `SendResult` or register callbacks to verify success/failure branches.

Example observing a callback:

~~~java
CompletableFuture<SendResult<String, String>> sendFuture =
        kafkaTemplate.send("orders.created", "order-1002", "payload");

CompletableFuture<RecordMetadata> callbackResult =
        new CompletableFuture<>();

sendFuture.whenComplete((result, exception) -> {
    if (exception != null) {
        callbackResult.completeExceptionally(exception);
    } else {
        callbackResult.complete(result.getRecordMetadata());
    }
});

RecordMetadata metadata =
        callbackResult.get(10, TimeUnit.SECONDS);

assertThat(metadata.topic()).isEqualTo("orders.created");
~~~

Using a secondary future lets the test wait deterministically for the callback result. There is no need for `Thread.sleep` to guess when the callback runs.

Scenarios to verify:

- Success callbacks receive `SendResult` and valid metadata.
- Failure callbacks receive the exception when the future fails.
- Callbacks do not turn a failed future into a fake success.
- Callbacks do not block producer threads with synchronous database queries or HTTP calls.
- `whenCompleteAsync` uses a bounded executor, and tests cover task-rejection behavior if that is part of application policy.

If a callback only logs or increments metrics, unit tests with mocks are usually enough. If a callback mutates business state, verify that state through collaborators or published outcomes explicitly.

## 8. Testing errors and retry limits

Not every producer failure is easy to trigger in integration tests. Stopping a broker mid-test, dropping network links, or altering ACLs can be useful but tends to introduce environment dependencies and flakiness.

Choose a testing approach suited to the goal:

| Scenario | Suitable testing approach |
|---|---|
| Future completes exceptionally | Unit test with a failed `CompletableFuture`. |
| Serialization error | Use real serializer with an invalid object or incompatible settings. |
| Broker unavailable | Failure test with a controlled stopped container/broker. |
| Timeout or network fault | Testcontainers and environment-appropriate fault injection. |
| Missing write permission | Test Kafka cluster with ACLs enabled and restricted credentials. |
| Retry limit exceeded | Policy unit test or integration test with deterministic timeout. |

When testing retries, verify attempt counts, backoff intervals, or final state against policy. Avoid unbounded retries, which can hang tests or exhaust resources.

Also distinguish internal Kafka producer retries from application-triggered retries after a future fails. An idempotent producer handles internal retries within Kafka's guarantees; it does not deduplicate a brand-new application `send` call issued after an uncertain previous outcome.

If the application retries a business event, keep `eventId` stable and design idempotent consumers. Tests should verify repeated sends do not create duplicate business side effects, even if the topic contains multiple records with the same `eventId` under uncertain failure conditions.

## 9. EmbeddedKafka vs. Testcontainers: which to choose?

Both EmbeddedKafka and Testcontainers support integration testing, though they fit different needs.

| Criterion | EmbeddedKafka | Testcontainers |
|---|---|---|
| Purpose | Fast integration tests inside the test JVM | Testing against a broker running in a container |
| Startup | Generally fast and convenient for Spring Kafka tests | Depends on Docker and container startup time |
| Broker setup | Suited to focused test scenarios | Can mirror deployment image and version closely |
| Multi-broker | Supported depending on test setup and version | Can spin up multi-broker clusters when needed |
| Deployment networking | Does not fully represent production networking | Can verify port mappings and container addressing |
| When to use | Producer/consumer logic, metadata, serialization, and callbacks | Broker compatibility, security, multi-broker setups, and production-like behavior |

EmbeddedKafka works well to validate KafkaTemplate and listeners inside a lightweight test context. Testcontainers is better when differences between an embedded test broker and production brokers could affect results, or when testing specific broker settings.

With Testcontainers, bootstrap addresses must be retrieved dynamically from the container rather than hardcoded to `localhost`. Example Spring test configuration:

~~~java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.kafka.bootstrap-servers",
            kafkaContainer::getBootstrapServers
    );
}
~~~

`kafkaContainer` must be declared and started using the Testcontainers Kafka module matching your project's dependency version. Package names and container classes can differ across versions; use the exact API included in your build.

You do not need Testcontainers for every unit test. Starting containers only for tests that genuinely require a broker keeps the test suite fast and reliable.

## 10. Isolating data and avoiding order-dependent tests

Kafka is a log-storage system. Records from an earlier test can remain in a topic and be read by a later test if topics, group IDs, or offsets are shared.

To keep tests independent:

- Use test-specific topics or unique topic names per test run.
- Use dedicated consumer groups to avoid reusing offsets from other tests.
- Configure `auto.offset.reset` intentionally when a group has no committed offsets yet.
- Create the consumer before sending if the test expects to read new records immediately afterward.
- Read the exact number of expected records with explicit timeouts.
- Close test-created consumers and producers in `finally` or `try-with-resources`.
- Avoid deleting shared topics while other tests might still be using them.
- Never depend on test execution order or leftover broker state from prior runs.

A common pitfall is reusing a fixed consumer group across multiple tests. Once the group commits offsets from an earlier run, a later test might skip records even with `auto.offset.reset=earliest`. `auto.offset.reset` only applies when a group lacks valid committed offsets; it never overrides committed offsets.

If tests run in parallel, assign unique topics and group IDs per test or per test worker. Resource cleanup must be designed not to delete topics in active use by another test.

## 11. Testing transactions and acknowledgement levels

If a producer uses `acks=all`, tests can verify the future completes and metadata is returned after broker acknowledgement according to ISR settings. However, tests must not infer from a success callback that a consumer processed the record or a database committed.

For Kafka transactions, test two layers:

- The send future of each record.
- The commit or abort outcome of the transaction.

A send may receive broker results while the transaction is still open. A consumer configured with `isolation.level=read_committed` only reads records from committed transactions. Therefore, transaction tests should cover both commit and abort branches and use a `read_committed` consumer to verify which records are visible.

Kafka transactions do not cover external databases or APIs. If a producer emits events tied to database changes, test outbox/inbox or idempotency at the corresponding data boundary.

## 12. Workflow for building a producer test suite

You can build the suite in the following order:

1. Write unit tests for the service building events, selecting topic/key, and calling KafkaTemplate.
2. Verify the returned future and proper exception preservation.
3. Set up EmbeddedKafka to confirm records are actually written.
4. Read records back to verify key, value, headers, partition, and offset.
5. Add round-trip tests for real serializers/deserializers.
6. Test success and failure callbacks.
7. Add bounded retry tests and verify idempotency if the application retries at the business level.
8. Use Testcontainers for scenarios needing production-like brokers or networking.
9. Isolate topics and group IDs so tests run independently and in parallel.
10. Integrate broker-dependent tests into CI pipelines with explicit timeouts and resource cleanup.

Not every code change needs to run full cluster tests. Unit tests should run frequently; integration tests run in the appropriate pipeline stage; network-fault or multi-broker tests can live in dedicated suites.

## 13. Comprehensive exercise: testing OrderEventPublisher

Build `OrderEventPublisher` to send `OrderCreatedEvent` to the `orders.created` topic.

Requirements:

1. Write a unit test verifying the publisher calls KafkaTemplate with the right topic, `orderId` as key, and event as value.
2. Verify the publisher returns the exact `CompletableFuture`.
3. Create a failed future to verify errors are preserved and failure callbacks trigger.
4. Use EmbeddedKafka to send records to an embedded broker.
5. Read back `ConsumerRecord` and assert key, payload, topic, partition, and offset.
6. Test the `correlation-id` header.
7. Use the application's real serializer/deserializer to verify JSON round-trip.
8. Test the success callback and measure send completion time.
9. Create a bounded failure test to verify retry policy.
10. If the application retries events, resend the same `eventId` and verify the consumer does not duplicate business effects.
11. Use Testcontainers if you need to verify broker version, security, or networking.
12. Run tests in parallel to verify topic and consumer-group isolation.

The test suite is complete when it proves all three layers: the service calls KafkaTemplate properly, the broker receives the record and returns metadata, and the consumer reads back records matching the contract. On failure paths, tests must prove the application detects failure, preserves root-cause information, and applies bounded retries.

## 14. Learning sequence and completion criteria

| Stage | Core focus | Self-check criterion |
|---|---|---|
| 1. Unit test | Mockito and KafkaTemplate | Verify topic, key, value, and returned future. |
| 2. Future/error | `CompletableFuture`, exceptions | Test both success and failure outcomes. |
| 3. Broker test | EmbeddedKafka | Send and read back real records. |
| 4. Metadata | `SendResult`, `RecordMetadata` | Verify topic, partition, and offset. |
| 5. Serialization | JSON or schema serializers | Round-trip payloads match the contract. |
| 6. Callback | `whenComplete` and `whenCompleteAsync` | Callbacks run on the right branch without blocking the producer. |
| 7. Reliability | Retries, idempotence, `eventId` | Bounded retries and safe duplicate handling are tested. |
| 8. Container test | Testcontainers | Broker and production-like configuration are verified. |
| 9. Isolation | Topics, group IDs, cleanup | Tests run independently, repeatedly, and in parallel reliably. |

The lesson is complete when you have unit tests verifying the publisher contract, integration tests proving records are written and read back, and checks for metadata, serialization, callbacks, and errors. Keep a clear boundary between broker record acknowledgement and consumer business completion; those two outcomes require different tests.

KafkaTemplate makes sending records in Spring convenient, but testing only at the service layer is not enough to prove a messaging flow works. Combining unit tests, EmbeddedKafka or Testcontainers, metadata checks, and record read-backs catches configuration, serialization, connectivity, and asynchronous handling bugs early.

