# Goals of Messaging Testing

Spring Kafka applications communicate through asynchronous flows. A producer may send successfully while a consumer processes later; a listener may retry, commit offsets, forward records to a dead-letter topic, or participate in transactions. Therefore, the goal of messaging testing is not merely to verify that a Java method was called, but to prove that **records are constructed properly, transmitted through Kafka according to contract, processed by the consumer under the desired delivery semantics, and recovered properly on failure**.

A good test suite answers key questions: does the producer serialize properly, does the listener receive the right payload and metadata, do offsets advance at the right time, are retries bounded, do failed records reach the DLT, do transactions commit/roll back atomically, and does the application tolerate duplicates or restarts.

## 1. Why Messaging Needs Dedicated Testing

A synchronous method call usually produces a result immediately within the same call stack. Kafka works differently: the producer sends a record over the network, the broker stores the record, the consumer polls by partition, the listener processes on a separate thread, and offsets are committed according to container configuration.

```text
Producer application
      |
      | serialize + send
      v
Kafka broker / topic / partition
      |
      | consumer poll
      v
Spring Kafka listener container
      |
      | deserialize + convert
      v
@KafkaListener
      |
      | business processing
      v
Database / downstream service
      |
      v
Acknowledgment / offset commit
```

Failures can happen at every boundary: serialization, network, broker, deserialization, listener, database, acknowledgment, or commit. Unit tests for a business service do not prove that these boundaries work together.

Messaging tests need to cover at least four categories of behavior:

- **Correctness:** payload, key, headers, topic, and partition match the contract.
- **Delivery:** records are processed under the chosen at-most-once, at-least-once, or transactional semantics.
- **Failure handling:** retry, recovery, DLT, and redelivery work properly.
- **Operational behavior:** concurrency, ordering, rebalance, pause, timeout, and shutdown do not produce invalid state.

## 2. Testing Goals by Component

| Component | What to Prove |
| --- | --- |
| Producer/application service | Creates the right event, key, topic, and headers; handles send failure properly |
| Serializer | Object is converted into wire bytes matching the contract |
| Deserializer/converter | Bytes are converted into payload/headers of the expected type |
| Kafka broker/topic | Partitioning, retention, compaction, and required configurations match |
| Consumer/listener container | Poll, assignment, concurrency, and listener invocation are correct |
| Listener/business service | Processes data properly and is idempotent on redelivery |
| Offset/acknowledgment | Advances offsets only at the defined processing point |
| Error handler/retry | Retries the right number of times, with the right backoff and exception types |
| DLT/recovery | Failed records are forwarded with sufficient metadata for investigation |
| Transaction | Output and input offsets commit or abort together |
| Schema/contract | Producer and consumer remain compatible across data versions |

Not every test needs to verify all of these items. Choose the testing layer that fits the question being asked.

## 3. Layering Tests

A practical strategy typically has three main layers:

| Layer | Common Tools | Scope |
| --- | --- | --- |
| Unit test | JUnit, Mockito, AssertJ | Business logic, mapping, validation, exception classification |
| Integration test | `spring-kafka-test`, Embedded Kafka, Testcontainers | Producer/consumer, serializer, listener container, offset, retry, DLT, transaction |
| Contract/system test | Schema Registry compatibility check, production-like broker, staging environment | Wire contract, ACL/TLS, multiple services, replay, and end-to-end operations |

Unit tests run fast and in isolation, but do not fully simulate the Kafka protocol. Integration tests verify the connection between Spring Kafka and the broker. Contract/system tests verify that independent services actually understand the same data and production configuration.

There is no need to start a broker for every test. Business rules should be verified with unit tests; Kafka-dependent behaviors require integration tests with a real or compatible test broker.

## 4. Testing Business Logic Independently of Kafka

Separating business logic from the listener makes testing easier and faster. The listener simply receives the payload, delegates to a service, and lets exceptions/acknowledgment follow the container policy.

Example service:

```java
public class OrderProjectionService {

    private final OrderRepository repository;

    public OrderProjectionService(OrderRepository repository) {
        this.repository = repository;
    }

    public void process(OrderCreatedEvent event) {
        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        repository.save(new OrderProjection(
                event.orderId(), event.total(), event.currency()));
    }
}
```

Unit tests focus on business rules:

```java
@ExtendWith(MockitoExtension.class)
class OrderProjectionServiceTest {

    @Mock
    OrderRepository repository;

    @Test
    void savesProjectionFromEvent() {
        var service = new OrderProjectionService(repository);
        var event = new OrderCreatedEvent(
                "evt-1", "ord-42", 125000L, "VND");

        service.process(event);

        verify(repository).save(argThat(projection ->
                projection.orderId().equals("ord-42")
                        && projection.total() == 125000L
                        && projection.currency().equals("VND")));
    }

    @Test
    void rejectsMissingOrderId() {
        var service = new OrderProjectionService(repository);
        var event = new OrderCreatedEvent("evt-2", " ", 100L, "VND");

        assertThrows(IllegalArgumentException.class,
                () -> service.process(event));

        verifyNoInteractions(repository);
    }
}
```

These tests do not need a Kafka broker. They prove mapping and business rules, while whether the listener deserializes properly and invokes the service is verified in integration tests.

## 5. Testing Producers

Producer tests need to verify that the application sends the right:

- Destination topic.
- Key and partitioning strategy.
- Serialized payload.
- Business/technical headers.
- Callback or future on send success/failure.
- Behavior when the broker is unavailable or the serializer throws an error.

With `KafkaTemplate`, `send` returns a `CompletableFuture<SendResult<K,V>>` in modern Spring Kafka versions. You can wait for the result in a test with a timeout:

```java
@Test
void publishesOrderEvent() throws Exception {
    var event = new OrderCreatedEvent("evt-1", "ord-42", 125000L, "VND");

    var result = kafkaTemplate
            .send("orders.created", "ord-42", event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
            .isEqualTo("orders.created");
    assertThat(result.getRecordMetadata().partition())
            .isGreaterThanOrEqualTo(0);
}
```

This example assumes the producer factory is configured with a serializer suitable for `OrderCreatedEvent`. It proves the broker acknowledged the record and returned metadata; to verify the actual payload, consume the record with a consumer using the matching deserializer.

Do not test merely by asserting that `KafkaTemplate.send()` does not throw an exception immediately. Sending is asynchronous; errors may appear later in the future or callback.

## 6. Testing Serializers and Deserializers

Serialization is part of the wire contract. Serializer/deserializer unit tests can verify:

- DTOs are converted into bytes in the expected format.
- Consumers reconstruct the exact values and data types.
- Nulls, optional fields, defaults, enums, and timestamps are handled properly.
- Old payloads can still be read according to the compatibility policy.
- Invalid-schema payloads or corrupted bytes produce predictable errors.

For JSON, check field names, numeric types, date/time formats, and unknown-properties policies. For Avro/Protobuf, check generated classes, schema IDs, defaults, field numbers, and schema resolution. If using Schema Registry, add registration/compatibility tests in CI or a test registry environment.

A test that serializes and deserializes the same version only proves that the two sides match each other. It does not prove that a new consumer can read payloads from an old producer. Keep representative byte/payload fixtures for all still-supported schema versions and run compatibility tests against them.

## 7. Testing Listeners with Embedded Kafka

`spring-kafka-test` provides `@EmbeddedKafka` to run a Kafka broker in the same test process. This is a convenient choice for Spring Kafka integration tests without installing a separate broker.

The test dependency typically looks like:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Example of testing a listener inside a Spring context:

```java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderListenerIntegrationTest {

    @Autowired
    KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    @Autowired
    OrderProjectionRepository repository;

    @Test
    void consumesOrderCreatedEvent() throws Exception {
        var event = new OrderCreatedEvent(
                "evt-test-1", "ord-test-42", 125000L, "VND");

        kafkaTemplate.send("orders.created", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
                assertThat(repository.findByOrderId("ord-test-42"))
                        .isPresent());
    }
}
```

This example requires Awaitility and the corresponding model/repository in the test project. `@EmbeddedKafka` sets the bootstrap server into the specified property so the Spring Boot producer/consumer connects to the test broker. Use a separate group ID per test context and clean repository data between tests to avoid execution-order dependencies.

## 8. Waiting for Asynchronous Results Properly

Kafka listeners run on separate consumer threads. When a test sends a record, `send().get()` only confirms that the producer received an acknowledgment; it does not mean the listener has finished processing.

To wait for the listener, use a synchronization mechanism with a timeout:

```java
await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
        assertThat(testProbe.receivedEvents())
                .extracting(OrderCreatedEvent::orderId)
                .contains("ord-42"));
```

Or use a `CountDownLatch`/`BlockingQueue` in a test probe. Avoid `Thread.sleep(500)` followed by an immediate assertion because poll timing, broker scheduling, CI load, and rebalances can vary.

Timeouts should be long enough to detect failures without making the suite sluggish. When a timeout occurs, also log the topic, group ID, listener assignment, and consumer lag to make diagnosis clearer.

## 9. Testing Keys, Partitions, Ordering, and Consumer Groups

Partitioning tests should send multiple records with different keys and verify partition metadata. If business logic requires events for the same aggregate to go to the same partition, send multiple events with the same key and verify they are written to the same partition.

Ordering is only guaranteed within a single partition. Tests should verify offset ordering within a partition rather than assuming global ordering across multiple partitions.

Consumer groups need tests for the following behaviors:

- Two consumers in the same group split partitions and do not process the same partition at the same time.
- Two different group IDs independently receive the same record.
- Increasing concurrency does not create useful parallelism beyond the number of assigned partitions.
- Restarting a consumer or adding an instance triggers a rebalance, but records are not dropped according to the delivery semantics.

For stable tests, create topics with an explicit partition count and wait for container assignment before sending records. Do not rely on default partitions created by broker auto-creation.

## 10. Testing Offsets and Acknowledgments

Offsets are part of correctness. With `AckMode.RECORD`, `BATCH`, `MANUAL`, or `MANUAL_IMMEDIATE`, commit timing differs. Tests must prove that offsets only advance after the processing point defined by the application.

Important scenarios:

- Listener succeeds and the offset is committed.
- Listener throws an exception before acknowledgment; the record is retried/redelivered.
- Manual ack is only called after side effects complete.
- Application stops between a business commit and a Kafka offset commit; the record may be redelivered.
- `asyncAcks` receives out-of-order acknowledgments and the container waits for offset gaps.
- Batch listener processes partially and then fails; check which part is retried/recovered.

Do not assert only the number of listener invocations. Inspect the final state of the database/output topic and consumer group offsets when tests require specific commit semantics.

## 11. Testing Retries and Error Handlers

Retry tests should verify invocation count, backoff intervals at an appropriate level, exception classification, and final outcome.

Example using a service mocked to fail twice then succeed:

```java
@Test
void retriesTransientFailureAndEventuallyProcesses() {
    doThrow(new TransientDataAccessException("temporary") {})
            .doThrow(new TransientDataAccessException("temporary") {})
            .doNothing()
            .when(orderService).process(any());

    // Send event to the test broker and wait for the side effect to succeed.

    await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
            verify(orderService, times(3)).process(any()));
}
```

This illustrates the behavior for a `void` method; configure `DefaultErrorHandler` with small retry counts/backoff for tests and register the mock service in the Spring test context (using `@MockitoBean` or the mock bean mechanism matching your Spring Boot/Spring Framework version). Do not use long production backoffs in tests.

Also verify:

- Retryable exceptions are retried.
- Non-retryable exceptions go straight to recovery according to classification.
- Once retries are exhausted, the recoverer is invoked.
- A failure in the recoverer does not cause the offset to be committed as if recovery succeeded.
- `ackAfterHandle`, `commitRecovered`, and `AckMode` interact according to configuration.
- Deserialization errors occurring before the listener are handled via `ErrorHandlingDeserializer`.

## 12. Testing Dead Letter Topics

A DLT integration test should send a record guaranteed to fail, wait for the record to appear on the DLT, and verify both payload and metadata:

- Payload or raw bytes are preserved according to the recoverer configuration.
- Original headers such as topic, partition, and offset are recorded.
- Exception class/message and delivery attempt are present according to policy.
- DLT partitions are sufficient to accept the original partition if the resolver preserves the partition index.
- Input offset advances only after recovery publish succeeds according to configuration.
- A DLT consumer can read and inspect the record.

Do not merely verify that the listener stops receiving the record. That could happen because the container stopped, the record was skipped, or the offset was committed incorrectly. Consume from the DLT and inspect the actual contents.

## 13. Testing Non-Blocking Retry Topics

With `@RetryableTopic`, tests need to cover the main/retry/DLT topology:

1. Send a record to the main topic.
2. Have the listener fail on the first attempt and confirm the record is published to the retry topic.
3. Verify the main listener can continue processing subsequent records while the failed record waits.
4. Wait for the retry listener to receive the record after the backoff and confirm success or progression to the next retry stage.
5. Have a record exhaust all attempts and verify it lands in the DLT.
6. Verify keys, headers, and partition mapping according to configuration.

Do not assert exact retry timestamps. Backoff is a minimum wait time by mechanism; poll interval, scheduling, and consumer lag can delay record processing.

Non-blocking retry does not support batch listeners and does not combine with container transactions. Tests should reflect the chosen architecture rather than combining incompatible modes.

## 14. Testing Kafka Transactions and Exactly-Once

Transaction tests must use a transaction-capable broker and a `read_committed` consumer to verify visibility. There are two basic paths:

**Commit:** listener reads input, sends output using a `KafkaTemplate` sharing the `ProducerFactory`, and completes successfully; output and input offsets commit together.

**Abort:** listener sends output and then throws an exception; the transaction rolls back; a `read_committed` consumer does not see the aborted output, and the input record is retried according to `AfterRollbackProcessor`.

In addition, test producer fencing with transactional IDs, transaction timeouts, consumer restarts, and multiple instances with distinct prefixes if those are production risks to control.

Do not use `read_uncommitted` to verify EOS visibility because that consumer can see records from uncommitted or aborted transactions.

## 15. Testing Schema Evolution and Contracts

Store fixtures representing old schema versions and check whether the current consumer can read them. When a schema changes:

- Validate the new payload against the schema.
- Run compatibility checks against the Registry's subject/policy.
- Verify the producer serializes the right schema ID and wire format.
- Verify the consumer deserializes both old and new data.
- Check optional fields, nulls, defaults, new enums, and timestamps.
- Replay representative fixtures or historical data.

A producer and consumer sharing a new DTO may pass integration tests yet still break older services. Contract testing must include independent versions that are still supported.

## 16. Embedded Kafka or Testcontainers?

| Criterion | Embedded Kafka | Testcontainers Kafka |
| --- | --- | --- |
| Execution model | Test broker in the test process | Broker running in a container |
| Startup speed | Usually fast for Spring Kafka tests | Usually slower due to container initialization |
| Environment | Convenient for listener, producer, offset, and retry tests | Closer to deployed broker environment when choosing matching image/config |
| Broker configuration | Configurable, though typically focused on fast tests | Can test specific images/versions and broker configs |
| Environment dependency | No Docker required for embedded broker | Requires an available Docker runtime |
| Use case | Frequent integration tests in the suite | Broker compatibility tests, production-like transaction/security/config tests |

Choose the tool based on the goal. Embedded Kafka fits most Spring Kafka integration tests. Testcontainers is useful when testing a specific Kafka broker version, SSL/SASL listeners, transaction settings, or production-like configurations.

Do not use a mocked `KafkaTemplate` to prove Kafka protocol behavior, partition assignment, offset commits, or transactions. Mocks are only appropriate for verifying that a service calls the right API with expected arguments.

## 17. Test Isolation and Avoiding Flaky Tests

Messaging tests easily become flaky if multiple tests share topics, group IDs, offsets, or data. Principles:

- Use separate topics and group IDs per test class/run when isolation is needed.
- Initialize topics with an explicit partition count.
- Wait for the listener container to be assigned partitions before sending records.
- Clean database/test state between tests.
- Do not rely on test execution order or leftover offsets from previous runs.
- Use Awaitility, latches, or queues with timeouts instead of fixed sleeps.
- Close producers/consumers/containers and release brokers after tests.
- Keep backoffs and timeouts small yet sufficient to test the state transitions properly.
- Do not run tests sharing the same topic/group in parallel unless designed for isolation.

If a test fails intermittently, collect group rebalance logs, partition assignments, consumer lag, offsets, and listener container state instead of arbitrarily increasing timeouts.

## 18. Testing Security and Production Configuration

If the production application uses TLS, mTLS, SASL, or ACLs, dedicated tests are needed for security configuration:

- Clients verify the broker's CA and hostname properly.
- Valid client certificates are accepted when using mTLS.
- Invalid or expired certificates are rejected.
- Producers can only write to authorized topics.
- Consumers can only read authorized topics and groups.
- Transactional IDs have appropriate permissions when using Kafka transactions.
- Secrets do not appear in logs or test reports.

Not every unit test needs to run the full security suite. Security tests can run in an integration/security pipeline with a test broker configured with the corresponding SSL/SASL/ACL settings.

## 19. Performance and Load Testing

Performance tests answer throughput and latency questions under increasing load and do not replace correctness tests. Metrics to collect:

- Producer send rate, error rate, and request latency.
- Consumer records/sec and lag per partition.
- Listener processing time at p50/p95/p99.
- Retry rate, DLT rate, and backoff duration.
- Rebalance count/duration.
- CPU, heap, garbage collection, and thread count.
- Database/HTTP pool utilization and downstream latency.
- Transaction duration/abort rate if using EOS.

Load tests should use realistic key distributions to detect hot partitions. Increasing concurrency does not necessarily increase throughput if partition count, CPU, or downstream systems are already the bottleneck.

## 20. Reference Testing Matrix

| Area | Unit | Integration Broker | Contract/System |
| --- | :---: | :---: | :---: |
| Business rules and validation | ✓ |  |  |
| Event mapping | ✓ | ✓ |  |
| Serializer/deserializer | ✓ | ✓ | ✓ |
| Topic/key/partition |  | ✓ | ✓ |
| Listener invocation |  | ✓ | ✓ |
| Offset/acknowledgment |  | ✓ | ✓ |
| Retry/backoff/DLT |  | ✓ | ✓ |
| Non-blocking retry topology |  | ✓ | ✓ |
| Kafka transaction/EOS |  | ✓ | ✓ |
| Schema compatibility | ✓ | ✓ | ✓ |
| TLS/SASL/ACL |  | ✓ | ✓ |
| Throughput/latency |  |  | ✓ |
| Multi-service replay |  |  | ✓ |

This matrix is only a suggestion. Projects may shift certain tests to another layer depending on cost and required confidence.

## 21. Pre-Release Checklist

- [ ] Business logic has unit tests independent of Kafka.
- [ ] Producer tests verify send results and metadata.
- [ ] Serializers/deserializers have wire format tests and legacy fixtures.
- [ ] Listener integration tests run against a test broker.
- [ ] Tests use explicit topics, group IDs, and partition counts.
- [ ] Asynchronous tests wait using latches/queues/Awaitility with timeouts.
- [ ] Offsets and manual acknowledgments are verified according to AckMode.
- [ ] Retries, exception classification, and DLT are tested.
- [ ] Non-blocking retries are tested across both retry topics and DLT.
- [ ] Transaction commit/abort is verified using a `read_committed` consumer.
- [ ] Schema compatibility and cross-version fixtures are tested.
- [ ] TLS/SASL/ACL are tested in the appropriate pipeline.
- [ ] Performance tests use representative load and key distributions.
- [ ] Logs/metrics are sufficient to diagnose flaky tests and production incidents.

## 22. Conclusion

The goal of messaging testing is to prove the entire event exchange behavior, from wire contract to processing, offsets, retries, recovery, and failure handling. Unit tests protect business logic; integration tests with Embedded Kafka or Testcontainers verify Spring Kafka interacts properly with the broker; contract/system tests check compatibility across services and deployment environments.

Test along the real asynchronous boundaries: await producer futures, await listeners with latches/queues/Awaitility, and verify offsets and final state rather than relying on sleeps or single invocation counts. Cover redelivery, DLT, transaction rollback, schema evolution, and security according to risk level. A reliable messaging test suite helps catch bugs before events are lost, duplicated, or stuck in production.

## References

- [Spring for Apache Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Embedded Kafka Broker](https://docs.spring.io/spring-kafka/reference/testing.html#embedded-kafka)
- [Spring for Apache Kafka — KafkaTestUtils API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
