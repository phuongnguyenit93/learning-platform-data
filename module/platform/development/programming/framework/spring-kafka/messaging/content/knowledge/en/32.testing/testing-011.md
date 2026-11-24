# Testing Error Handlers

An error handler determines what happens when a listener fails to process a Kafka record: retry, wait through backoff, skip an exception type, forward the record to a Dead Letter Topic (DLT), or let the error continue under policy. A misconfiguration can cause records to retry endlessly, land in the DLT too early, or have offsets acknowledged while business work has not completed. Therefore, error handler tests must verify listener behavior, attempt count, recovered records, DLT metadata, and consumer group offset progression.

In Spring Kafka, `DefaultErrorHandler` is the standard common error handler for listener containers not using Kafka transactions. For transactional listeners, post-rollback handling is typically performed by an `AfterRollbackProcessor`, commonly `DefaultAfterRollbackProcessor`. The two mechanisms have different placement and semantics; tests must use the exact container type the application runs.

This lesson belongs to the **Testing** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups; as well as learning serialization, retries, dead-lettering, transactions, exactly-once, concurrency, and testing to operate reliable messaging flows.

## 1. Where Does the Error Handler Sit in the Processing Flow?

With a non-transactional record listener, the container invokes the listener. If the listener throws an exception, the container delegates the error to the common error handler. The handler can retry the record, seek the consumer, invoke a recoverer, or let the error continue under policy.

~~~mermaid
flowchart TD
    A[Kafka poll] --> B[Listener container]
    B --> C[@KafkaListener]
    C --> D{Processing succeeded?}
    D -->|Yes| E[Commit offset per AckMode]
    D -->|No| F[CommonErrorHandler]
    F --> G{Retries remaining?}
    G -->|Yes| H[Backoff and redeliver record]
    H --> C
    G -->|No| I[Recoverer]
    I --> J[DLT or recovery action]
    J --> K[Handle offset per recovery policy]
~~~

Points to test:

- How many times the listener is invoked for the same record.
- Whether backoff and exception classification behave properly.
- Whether the recoverer runs only when retries are exhausted or the error is classified as non-retryable.
- Whether the DLT contains the record with the expected payload, key, partition, and required headers.
- Whether source offsets advance only per configured policy.
- Whether a failing record does not cause independent records to be lost.

## 2. Distinguishing Types of Tests

Not every test needs to start Kafka. Choose the test level based on the behavior to confirm:

| Test Level | Components | Goal |
| --- | --- | --- |
| Unit test | Exception classifier, retry policy, resolver, recoverer wrapper | Verify pure rules and classification branches. |
| Component test | Listener, service, and handler inside Spring context | Verify wiring, dependency injection, and listener behavior. |
| Integration test | Spring Kafka container with Embedded Kafka or Testcontainers | Verify real polling, retries, DLT, serialization, and offsets. |
| System test | Kafka cluster and related services | Verify ACLs, broker failures, rebalances, and production-like operations. |

Mocking `KafkaConsumer` usually fails to prove seek, poll, group offset, or broker transaction semantics. Use unit tests for fast logic checks; use a real broker for behaviors depending on the Kafka protocol.

## 3. Dependencies for Testing

With Maven, add Spring Kafka test in `test` scope and use the version managed by Spring Boot dependency management or the Spring Kafka BOM:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

If using Testcontainers, add the Kafka module and JUnit integration matching the project's version:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>kafka</artifactId>
    <scope>test</scope>
</dependency>
~~~

Do not force a `spring-kafka-test` version different from `spring-kafka`. Spring Kafka testing APIs change across versions; use dependencies from the same version line as the runtime library. Examples in this lesson illustrate record listeners and common Spring Kafka 3.x APIs; for 2.x projects, check the corresponding API names in that exact version's Javadoc.

## 4. Configuring DefaultErrorHandler to Be Tested

A common configuration uses `DeadLetterPublishingRecoverer` and `FixedBackOff`:

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(100L, 2L)
        );

    handler.addNotRetryableExceptions(
        InvalidOrderEventException.class
    );

    return handler;
}
~~~

With `FixedBackOff(100L, 2L)`, the initial delivery plus two retries yields at most three listener invocations before recovery, assuming no other policy changes the behavior. `addNotRetryableExceptions` places the specified exception into the non-retryable group under the handler's classifier.

Retries can be recorded using `RetryListener`:

~~~java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        retryMetrics.record(record.topic(), deliveryAttempt);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        recoveryMetrics.increment(record.topic());
    }
});
~~~

Add tracking listeners only if the application needs metrics or auditing. Tests should not rely on log messages; prefer asserting invocation counts, recovery results, and DLT records.

## 5. Testing Exception Classification

Exception classification determines which failures are retried. For example, transient infrastructure errors can be retried, whereas contract-violating payloads should usually recover immediately.

A test listener can throw two distinct exception types:

~~~java
@Component
public class OrderListener {

    private final AtomicInteger transientAttempts = new AtomicInteger();

    @KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-test-group"
    )
    public void listen(String payload) {
        if (payload.equals("temporary")) {
            if (transientAttempts.getAndIncrement() < 2) {
                throw new TransientOrderException("Temporary failure");
            }
        }

        if (payload.equals("invalid")) {
            throw new InvalidOrderEventException("Invalid payload");
        }

        process(payload);
    }
}
~~~

Tests need to verify:

- `temporary` is retried per retry policy and eventually succeeds.
- `invalid` is not retried when configured as non-retryable.
- Exceptions not listed in the classifier still match the active version's default classification behavior.
- Wrapped exceptions with a cause chain are classified according to configured rules.

Do not merely assert that `addNotRetryableExceptions` was called during configuration. Send real records and verify the listener invocation count to test wiring from container to handler.

## 6. Unit Testing Retry Policies and Destination Resolvers

Pure rules such as topic/partition mapping can be tested without a broker:

~~~java
@Test
void shouldRouteFailedRecordToMatchingDltPartition() {
    ConsumerRecord<String, String> record =
        new ConsumerRecord<>(
            "orders",
            2,
            105L,
            "order-42",
            "invalid"
        );

    TopicPartition destination =
        new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        );

    assertThat(destination.topic()).isEqualTo("orders.DLT");
    assertThat(destination.partition()).isEqualTo(2);
}
~~~

This test only checks the routing rule. It does not prove the DLT topic exists, that the serializer can publish the record, or that the source offset is committed.

For custom resolvers, also test cases such as:

- Different source topics.
- Source partitions at topology boundaries.
- Partitions remapped via modulo.
- Exception types changing the destination.
- Invalid destinations failing clearly.
- Raw key/value bytes preserved when handling deserialization failures.

For `BackOff`, you can check `nextBackOff()` counts and `STOP` state in a dedicated unit test. Integration tests must still verify that the handler actually applies that policy.

## 7. Integration Testing with Embedded Kafka

`@EmbeddedKafka` starts an embedded broker for tests, making it possible to test listener containers, producers, consumers, and DLTs without an external cluster.

Example declaration:

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders", "orders.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderErrorHandlerIntegrationTest {
    // Tests using real KafkaTemplate and listener container.
}
~~~

Test application configuration should disable auto-commit and use a dedicated group ID for tests. The DLT needs a matching partition count if the default recoverer preserves the source partition. When tests run in parallel, each test class or test case needs separate topics/groups or explicit cleanup to avoid reading records from a previous run.

Embedded Kafka fits fast integration tests. It does not fully replace tests with a broker/container version matching production, especially for ACLs, TLS, broker rolling restarts, replication, and multi-node cluster failure modes.

## 8. Creating a Test Consumer to Read the DLT

Subscribe the DLT consumer before sending failing records. Use a dedicated group ID, `auto.offset.reset=earliest`, and deserializers compatible with the published data types.

Helper example:

~~~java
private Consumer<String, String> createDltConsumer(
        EmbeddedKafkaBroker embeddedKafka) {

    Map<String, Object> props =
        KafkaTestUtils.consumerProps(
            "dlt-test-" + UUID.randomUUID(),
            "false",
            embeddedKafka
        );

    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    Consumer<String, String> consumer =
        new KafkaConsumer<>(props);

    embeddedKafka.consumeFromAnEmbeddedTopic(
        consumer,
        "orders.DLT"
    );

    return consumer;
}
~~~

`KafkaTestUtils.consumerProps` names and overloads vary across Spring Kafka lines. If the compiler rejects the overload above, use the signature provided by your project's dependency version; the goal is creating a consumer with bootstrap servers from Embedded Kafka, a dedicated group ID, and auto-commit disabled.

Close the consumer in `finally` or try-with-resources. Do not leave test consumers running in the background after tests end, as they retain threads and leak resources.

## 9. Testing That Failed Records Route to the DLT

Given a payload that always makes the listener throw `InvalidOrderEventException` configured as non-retryable, the test can send the record and read from the DLT:

~~~java
@Test
void invalidRecordShouldBePublishedToDlt() {
    try (Consumer<String, String> dltConsumer =
             createDltConsumer(embeddedKafka)) {

        kafkaTemplate.send("orders", "order-42", "invalid");

        ConsumerRecord<String, String> dltRecord =
            KafkaTestUtils.getSingleRecord(
                dltConsumer,
                "orders.DLT",
                Duration.ofSeconds(10)
            );

        assertThat(dltRecord.key()).isEqualTo("order-42");
        assertThat(dltRecord.value()).isEqualTo("invalid");
    }
}
~~~

Tests must verify the destination topic, key/value, partition per resolver, and metadata headers. If the DLT consumer receives the record after a wait, use a timeout long enough for CI environments without fixed sleeps.

If the listener can process the record successfully after a retry, that record should not appear in the DLT. Test the success-after-retry and exhausted-retry branches separately so a single assertion does not hide policy bugs.

## 10. Verifying Retry Attempt Counts

Counting listener invocations is a direct way to verify retry policy. Use an `AtomicInteger` or a thread-safe test probe because the listener runs on a consumer thread.

Example with two retries after the first attempt:

~~~java
@Test
void transientFailureShouldBeRetriedBeforeSuccess() {
    kafkaTemplate.send("orders", "order-7", "temporary");

    await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
            assertThat(listener.transientAttempts()).isEqualTo(3)
        );

    assertThat(listener.processedOrderIds())
        .contains("order-7");
}
~~~

The exact count depends on `BackOff`, classifier, recoverer, and how the listener is written. With `FixedBackOff(interval, maxAttempts)`, `maxAttempts` is the number of retries after the first attempt, not the total invocation count.

Do not assert millisecond-exact timings in integration tests. Schedulers, broker startup, and CI load cause real timing to fluctuate. Test policies by invocation count and use generous bounded timeouts for final outcomes.

## 11. Verifying DLT Metadata

The DLT must hold more than just the payload; records must contain sufficient metadata to trace back to the source. With the default `DeadLetterPublishingRecoverer`, Spring Kafka adds headers describing the original topic, partition, offset, timestamp, and exception.

Header check example:

~~~java
assertThat(dltRecord.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC))
    .isNotNull();

assertThat(dltRecord.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_PARTITION))
    .isNotNull();

assertThat(dltRecord.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET))
    .isNotNull();
~~~

Header values are byte arrays; when comparing values, decode according to the data type Spring Kafka writes into the header or use a test helper. Do not compare a `Header` object directly against a `String` or `Long`.

Also test:

- Original topic matches the source topic.
- Original partition and offset match the source record.
- Exception class/message are added per header configuration.
- Headers are not lost when using a custom destination resolver.
- DLT partition matches the preserve or remap policy.
- Key and payload remain intact if the serializer supports those data types.

If the application customizes headers via `setHeadersFunction` or `setExceptionHeadersCreator`, tests must verify both standard metadata and custom headers.

## 12. Verifying Offsets After Recovery

An integration test that only sees the record in the DLT does not prove the consumer group advanced past the source record. If the offset is not committed per recovery policy, the source record could be redelivered after a restart and land in the DLT again.

You can read committed offsets using `AdminClient`:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets =
    adminClient.listConsumerGroupOffsets("orders-test-group")
        .partitionsToOffsetAndMetadata()
        .get(10, TimeUnit.SECONDS);

OffsetAndMetadata committed =
    offsets.get(new TopicPartition("orders", sourcePartition));

assertThat(committed).isNotNull();
assertThat(committed.offset()).isGreaterThan(sourceOffset);
~~~

For deterministic results, send the record to a specific partition and save the metadata returned by `KafkaTemplate.send(...).get(...)`. Once DLT publishing finishes, wait until the committed offset advances past that source offset.

The committed offset represents the next position to read, so after record offset `n` is acknowledged, the committed offset is typically greater than `n` (usually `n + 1` if there are no gaps in that partition).

Offset assertions must account for `AckMode`, manual acknowledgment, container transactions, and `commitRecovered`. Do not hard-code expectations for a configuration different from the one under test.

## 13. Testing Recoverer Publish Failure

Recovery is complete only when DLT publishing satisfies the application's policy. If the DLT producer fails to send yet the handler treats the record as recovered, the source offset can advance and the record is lost from the pipeline.

You can configure the recoverer to check the send result:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(dltTemplate);

recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(5));
~~~

API names and timeout types may differ by Spring Kafka version; use the exact signatures from the active dependency.

Test the failure path by making the DLT producer unable to publish, such as targeting a nonexistent topic in an environment with auto-create disabled or using a producer with denied ACLs. Verify:

- Recovery is recorded as failed.
- The recovery exception is observed per handler configuration.
- The source offset does not advance as if recovery succeeded.
- Once DLT publishing recovers, the record can be reprocessed according to policy.
- Logs/metrics distinguish listener failures from DLT publish failures.

Do not merely mock `KafkaTemplate.send()` to throw an exception and conclude that broker-side authorization or topic routing is tested. Mocks fit unit tests; integration tests should verify broker-returned failures.

## 14. Testing Retry Listeners and Metrics

If the application uses a `RetryListener` to emit metrics, inject a thread-safe test probe and verify callbacks are invoked:

~~~java
public class RetryProbe implements RetryListener {

    private final AtomicInteger failedDeliveries = new AtomicInteger();
    private final AtomicInteger recoveredRecords = new AtomicInteger();

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        failedDeliveries.incrementAndGet();
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        recoveredRecords.incrementAndGet();
    }

    public int failedDeliveries() {
        return failedDeliveries.get();
    }

    public int recoveredRecords() {
        return recoveredRecords.get();
    }
}
~~~

Attach the probe to the handler in test configuration:

~~~java
handler.setRetryListeners(retryProbe);
~~~

After sending a failing record, wait for the probe to update and assert callback counts per the active version's semantics. `deliveryAttempt` usually starts from the first failed delivery; confirm values against the runtime version rather than assuming the counter always equals the retry count.

Production metrics should use bounded tags such as topic, exception class, and listener ID. Avoid using event IDs or offsets as metric labels because cardinality can grow without bound.

## 15. Testing Deserialization Failures

Deserialization failures occur before the listener receives a Java object. Therefore, tests for malformed JSON payloads must confirm the listener is not called while error handling still sends raw bytes to the DLT if that is the policy.

Configure the consumer to use `ErrorHandlingDeserializer` wrapping a delegate:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

In the test, send a byte payload that is not valid JSON to the source topic. Verify:

- Listener invocation count does not increase.
- Container error handling receives the deserialization exception.
- Recoverer publishes the failed record to the DLT as configured.
- Raw value bytes remain intact if preserving the original payload is required.
- Exception metadata/headers trace the root cause.

If the DLT template can receive both deserialized objects and raw `byte[]`, configure a multi-type serializer such as `DelegatingByTypeSerializer`. The DLT consumer in tests must read `byte[]` when checking deserialization failures; do not use `StringDeserializer` and assume bytes will automatically convert properly.

Test key deserialization failures and value deserialization failures separately because the two cases place headers and raw bytes in different positions. Also test valid tombstones/null values so real nulls are not confused with deserialization failures.

## 16. Testing Batch Listeners and BatchListenerFailedException

Batch listeners have different error handling semantics than record listeners. When a record inside a batch fails, the application can throw `BatchListenerFailedException` with the failing record's index so `DefaultErrorHandler` determines which slice to seek/retry per batch policy.

Illustrative example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-test",
    containerFactory = "batchListenerFactory"
)
public void listenBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            process(records.get(index).value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Batch record failed",
                exception,
                index
            );
        }
    }
}
~~~

`BatchListenerFailedException` constructors may vary across Spring Kafka versions. Tests must use the exact signature from the project's dependency.

Recommended assertions:

- Batch listener is invoked with a batch containing multiple records.
- Failing index matches the record that threw the exception.
- Records before the failing index are not reprocessed if policy commits the preceding slice.
- The failing record is retried according to backoff.
- Records after the failing one are seeked and redelivered per batch handler semantics.
- Once retries are exhausted, only the record recovered per policy goes to the DLT.

If a batch listener throws a generic exception without indicating the failed index, the handler may have to retry the whole batch. Test this separately and ensure batch business logic is idempotent.

## 17. Testing Transactional Listeners: Using AfterRollbackProcessor

If the container uses Kafka transactions, test the rollback path through `AfterRollbackProcessor` rather than applying `DefaultErrorHandler` expectations unchanged.

Transactional listener configurations usually include:

- Transactional `ProducerFactory` with a transaction ID prefix.
- `KafkaTransactionManager` attached to the listener container.
- Consumer auto-commit disabled.
- Downstream consumers using `read_committed`.
- `DefaultAfterRollbackProcessor` to retry/recover after transaction rollback.

Tests must verify that a listener exception rolls back the transaction, output records from aborted transactions are invisible to `read_committed` consumers, input offsets do not commit in failed transactions, and records are redelivered per the after-rollback policy.

When retries are exhausted and the processor sends the record to a DLT with `commitRecovered=true`, verify the DLT record appears and the source offset commits in a new recovery transaction. DLT publish failures must be tested separately.

Do not use `DefaultErrorHandler` as a substitute for testing `DefaultAfterRollbackProcessor`. The two processing paths have different lifecycles.

## 18. Testing AckMode and Manual Acknowledgments

Offset behavior depends on `AckMode` and how the listener acknowledges records. When testing an error handler, use the same `AckMode` as production.

| AckMode | What to Verify |
| --- | --- |
| RECORD | Offset is acknowledged after each record listener completes successfully. |
| BATCH | Offsets are acknowledged per poll batch after the batch completes. |
| MANUAL | Listener calls acknowledge according to application logic. |
| MANUAL_IMMEDIATE | Acknowledge may commit immediately when called on the consumer thread; behavior depends on thread and container configuration. |

With manual acknowledgment, also test cases where the listener throws an exception before and after calling `acknowledge`. Do not call `acknowledge` and then continue work that can fail if the application cannot accept an already-acknowledged record.

If using asynchronous acknowledgments or worker pools, verify acknowledgment ordering, out-of-order completion, rebalances, and shutdown for your exact version. Never test only the handler while ignoring the listener's offset contract.

## 19. Testing Concurrent Listeners

When container concurrency is greater than one, multiple child consumers can process records in parallel. Tests must avoid non-thread-safe counters or assuming global topic ordering.

Verify:

- Retries on one partition do not break processing on other partitions.
- DLT routing preserves the source partition per the resolver.
- Consumer group receives the expected assignment.
- Shared test state is protected with `AtomicInteger`, concurrent collections, or synchronization.
- Do not use the same event key if the test needs to prove independent parallel processing.
- Do not assert global ordering across partitions.

If a test focuses solely on error handling of a single record, set concurrency to one to reduce nondeterminism. Keep separate concurrency tests when multi-consumer behavior is the target under test.

## 20. Using Awaitility Instead of Sleep

Kafka processing is asynchronous. After calling `KafkaTemplate.send`, the listener is not guaranteed to finish by the next line.

Avoid:

~~~java
Thread.sleep(2_000);
assertThat(dltRecords).hasSize(1);
~~~

Use a bounded wait condition:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertThat(dltRecords()).hasSize(1)
    );
~~~

Or use `CountDownLatch` when the test needs to wait for a specific listener callback. Timeouts should be wide enough for CI yet not so long that failures drag out the test suite.

Do not poll a test consumer and assert immediately when no record is ready. `KafkaTestUtils.getSingleRecord` waits for a bounded duration; if calling `poll` manually, loop until a deadline and accumulate records instead of assuming one poll always returns results.

## 21. Keeping Tests Stable and Diagnosable

Common causes of flaky error handler tests:

- Creating a test consumer after records were published while using `latest` offset reset.
- Reusing a group ID so the consumer starts at an old committed offset.
- DLT topic having fewer partitions than the source topic while the resolver preserves partition index.
- Sharing topics and listener state across parallel tests.
- Failing to close consumers or stop listener containers.
- Using fixed sleeps instead of waiting on conditions.
- Asserting on log text instead of observing records/offsets.
- Backoff too long making the suite slow, or too short making race conditions hard to reproduce.
- Test producer/consumer serializers incompatible with DLT payloads.

Each test should use a unique event ID, unique group ID, and isolated topics where possible. When a test fails, log the topic, partition, offset, group ID, attempt count, and exception class. Avoid logging full sensitive payloads.

Use `@DirtiesContext` when a test genuinely mutates Spring context or container state that cannot be restored; do not add this annotation to every test because it restarts the context and lengthens the suite.

## 22. Error Handler Testing Checklist

Before considering error handling thoroughly tested, confirm:

1. Listener success does not enter retry or DLT.
2. Retryable exceptions are retried the exact number of times.
3. Non-retryable exceptions are recovered according to policy.
4. Exception cause chains are classified properly if the application wraps exceptions.
5. Backoffs and retry limits have dedicated tests.
6. Recoverer picks the right DLT topic and partition.
7. DLT preserves key, payload, and source metadata headers.
8. DLT publish failure does not treat the source record as recovered.
9. Committed offsets advance properly per `AckMode`/recovery policy.
10. Deserialization failures do not invoke the listener and raw bytes are preserved if required.
11. Key failures, value failures, and tombstones are distinguished.
12. Batch listeners identify the right failed index and redelivery range.
13. Transactional listeners are tested via `AfterRollbackProcessor`.
14. Downstream consumers use `read_committed` when verifying transaction visibility.
15. Manual acknowledgments and async handoffs have dedicated offset tests.
16. Concurrency/rebalances do not drop records or misroute them.
17. Tests use Awaitility/latches with timeouts rather than sleep.
18. Consumers, containers, and test brokers close cleanly in lifecycle hooks.

Testing error handlers must verify behavior from listener to broker: retry counts, backoff, exception classification, DLT publishing, and offset recovery. Unit tests fit pure rules; Embedded Kafka or Testcontainers is necessary to verify seek, poll, serialization, headers, and committed offsets. For transactional listeners, use `AfterRollbackProcessor` and verify transaction visibility separately so semantics are not confused with `DefaultErrorHandler`.

