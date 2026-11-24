# Testing Retries and Dead Letters

## 1. Objectives of Testing

In Spring Kafka, a listener can fail because a dependency is temporarily unavailable, data is invalid, or there is a programming bug. Retries allow reprocessing a record according to a configured policy. When a record cannot be processed after the allowed attempts, the application can move it to a dead-letter topic (DLT) for investigation and recovery.

Tests must prove the complete behavior:

- Records are redelivered the exact number of times configured by policy.
- Transient failures succeed once the dependency recovers.
- Persistent or non-retryable failures are forwarded to the DLT.
- The DLT preserves the payload, key, and required source metadata.
- Failures when publishing to the DLT are not mistaken for successful recovery.
- Offsets are acknowledged per policy after processing or recovery.
- Redelivered records do not duplicate business side effects.

For example, with the `orders` topic: a listener updates a projection in the database. If the database times out twice and then recovers, the record should process successfully on the next attempt. If the record has an invalid payload, the system should move it to `orders.DLT` per the retry policy so the main flow continues.

## 2. Distinguishing Blocking Retry vs. Non-Blocking Retry

Spring Kafka has two common retry approaches. Testing strategy depends on which mechanism the application uses.

| Criterion | Blocking Retry | Non-Blocking Retry |
|---|---|---|
| Common mechanism | `DefaultErrorHandler` and `BackOff` | `@RetryableTopic` |
| Where retries occur | Listener container redelivers the record on the source partition | Record is published to a delayed retry topic |
| Source partition | Usually blocked at the failing record during retries | Can continue processing subsequent records |
| Ordering | Preserves partition order better during in-place retries | May alter order as records move through retry topics |
| Testing focus | Listener invocation count, backoff, DLT, and offsets | Retry topic routing, delays, attempt counts, DLT, and ordering |
| Best suited for | Short retries, keeping partition stream ordered | Long retries, avoiding blocking the source partition |

Do not merge both mechanisms into a single generic test. With blocking retry, verify listener invocation count and recoverer behavior. With non-blocking retry, verify records travel through configured retry topics and eventually reach the DLT.

~~~mermaid
flowchart TD
    A["Record from orders topic"] --> B["Listener processes"]
    B --> C{"Succeeded?"}
    C -->|Yes| D["Commit offset per AckMode"]
    C -->|No: blocking| E["DefaultErrorHandler"]
    E --> F{"Retries remaining?"}
    F -->|Yes| G["BackOff then redeliver record"]
    G --> B
    F -->|No| H["DeadLetterPublishingRecoverer"]
    H --> I["orders.DLT"]
    C -->|No: non-blocking| J["Retry topic"]
    J --> K["Listener retries after delay"]
    K --> L{"Succeeded?"}
    L -->|Yes| D
    L -->|No, attempts exhausted| I
~~~

## 3. Required Testing Levels

| Level | Tools | Goal |
|---|---|---|
| Unit test | JUnit, Mockito, AssertJ | Verify exception classification, service call count, idempotency logic |
| Configuration test | Spring test context | Verify error handler, backoff, and recoverer are wired to the container factory |
| Integration test | Embedded Kafka or Testcontainers | Verify records are actually retried and DLT-published via a broker |
| Staging smoke test | Production-like Kafka cluster | Verify ACLs, serializers, retention, topic provisioning, and real config |

Unit tests do not prove that the Kafka broker wrote to the DLT or committed offsets. Integration tests with a real broker are required for those behaviors.

## 4. Preparing Testing Dependencies

With Gradle, add the Spring Kafka test dependency matching the active Spring Kafka version:

~~~gradle
dependencies {
    testImplementation "org.springframework.kafka:spring-kafka-test"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

`spring-kafka-test` provides Embedded Kafka, `KafkaTestUtils`, and utilities for waiting on container assignment. Do not force a `spring-kafka-test` version different from the `spring-kafka` version managed by Spring Boot unless intentional.

Embedded Kafka fits testing producers, consumers, retries, and DLT within a single test process. If needing to test production-like settings such as multi-node brokers, ACLs, TLS, or SASL, use Testcontainers with a broker configured accordingly or a staging cluster.

## 5. Creating Embedded Kafka and Test Topics

Example using JUnit 5 and Spring Boot:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "spring.kafka.consumer.enable-auto-commit=false"
})
@EmbeddedKafka(
    partitions = 1,
    topics = {
        "orders.transient",
        "orders.transient.DLT",
        "orders.permanent",
        "orders.permanent.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class RetryAndDltIntegrationTest {

    @Autowired
    KafkaTemplate<Object, Object> kafkaTemplate;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    RetryProbeListener probeListener;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    // Test methods are illustrated in subsequent sections.
}
~~~

Each source topic and DLT is pre-created with one partition so this example preserves partition numbers when forwarding records. In projects with parallel tests, use per-test-class topic names or separate brokers to avoid sharing data.

Older Spring Kafka versions use `spring.embedded.kafka.brokers` and different bootstrap server mapping. Use `bootstrapServersProperty` if supported by your version; otherwise map the property per that version's documentation.

`@DirtiesContext` closes the context after the test class, preventing test listener containers and consumer groups from leaking into other tests. It does not replace using dedicated topics/group IDs and proper test data cleanup.

## 6. Configuring DefaultErrorHandler and DLT Recoverer

For record listeners, `DefaultErrorHandler` manages retries. Once retries are exhausted, `DeadLetterPublishingRecoverer` publishes the record to the DLT.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class RetryTestConfiguration {

    @Bean
    DefaultErrorHandler retryErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

        // Failing to publish to DLT must be treated as a recovery failure.
        recoverer.setFailIfSendResultIsError(true);

        var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(200L, 2L)
        );

        handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class
        );

        return handler;
    }
}
~~~

`FixedBackOff(200L, 2L)` means waiting 200 ms between retries, with up to two additional retries after the initial processing attempt. If the listener always fails with a retryable exception, total invocations are three: one initial attempt and two retries.

`InvalidOrderPayloadException` is marked non-retryable in this example. Records hitting this exception go to recovery without waiting for two retries. Only classify an exception as non-retryable when retrying cannot make the data valid on its own.

`InvalidOrderPayloadException` is a business exception defined by the application, for example extending `RuntimeException`. In real configuration, place this class in the appropriate domain package and import it into retry configuration.

The DLT template needs serializers compatible with failed records. This test example uses String keys/values so the template can use `StringSerializer`. When testing deserialization errors, the original value can be a byte array; configure the DLT producer to support both `byte[]` and normal object types, such as a type-delegating serializer. Do not assume `KafkaTemplate<Object,Object>` automatically serializes every type.

## 7. Attaching the Error Handler to the Listener Container Factory

Simply declaring a `DefaultErrorHandler` bean is not enough if the active container factory does not pick up that bean. Attach the handler to the factory referenced by the listener:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
        retryContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                DefaultErrorHandler retryErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(retryErrorHandler);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

The listener in tests must reference the exact factory:

~~~java
@KafkaListener(
    id = "permanentListener",
    topics = "orders.permanent",
    groupId = "retry-permanent-test",
    containerFactory = "retryContainerFactory"
)
public void handle(String payload) {
    // Call service or simulate failure.
}
~~~

If the test listener uses the default factory while the error handler is attached to `retryContainerFactory`, the test will not verify the intended configuration. Set an explicit `id` to fetch the container from `KafkaListenerEndpointRegistry` and wait for assignment before sending records.

## 8. Creating a Listener Simulating Transient and Permanent Failures

For repeatable retry tests, use per-message-ID counters instead of a single uncontrolled global counter:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class RetryProbeListener {

    private final Map<String, AtomicInteger> attempts =
        new ConcurrentHashMap<>();

    private final CountDownLatch transientSucceeded =
        new CountDownLatch(1);

    @KafkaListener(
        id = "transientListener",
        topics = "orders.transient",
        groupId = "retry-transient-test",
        containerFactory = "retryContainerFactory"
    )
    public void handleTransient(String messageId) {
        int attempt = attempts
            .computeIfAbsent(messageId, key -> new AtomicInteger())
            .incrementAndGet();

        if (attempt < 3) {
            throw new IllegalStateException("Dependency is temporarily unavailable");
        }

        transientSucceeded.countDown();
    }

    @KafkaListener(
        id = "permanentListener",
        topics = "orders.permanent",
        groupId = "retry-permanent-test",
        containerFactory = "retryContainerFactory"
    )
    public void handlePermanent(String messageId) {
        attempts
            .computeIfAbsent(messageId, key -> new AtomicInteger())
            .incrementAndGet();

        throw new IllegalStateException("Permanent processing failure");
    }

    public int attemptsFor(String messageId) {
        var counter = attempts.get(messageId);
        return counter == null ? 0 : counter.get();
    }

    public boolean awaitTransientSuccess(long timeout, TimeUnit unit)
            throws InterruptedException {
        return transientSucceeded.await(timeout, unit);
    }
}
~~~

The transient listener fails on the first two attempts and succeeds on the third. The permanent listener always fails so the error handler moves the record to the DLT once retries are exhausted.

In real tests, separate probe listeners per class or use a unique message ID for each test. Do not reuse the same message ID if the counter remains inside the Spring context.

## 9. Testing Retry Success After Transient Failure

Tests must wait for the listener container to receive partition assignment before sending records. This prevents a race condition where the producer sends before the consumer starts polling.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.kafka.core.KafkaTemplate;

// Place this method inside RetryAndDltIntegrationTest from section 5.
@Test
void retriesTransientFailureThenSucceeds() throws Exception {
    var container = registry.getListenerContainer("transientListener");
    ContainerTestUtils.waitForAssignment(container, 1);

    kafkaTemplate.send(
        "orders.transient",
        "transient-001",
        "transient-001"
    ).get(10, TimeUnit.SECONDS);

    assertThat(
        probeListener.awaitTransientSuccess(10, TimeUnit.SECONDS)
    ).isTrue();

    assertThat(probeListener.attemptsFor("transient-001"))
        .isEqualTo(3);
}
~~~

Expected outcomes:

- Producer sends the request record successfully.
- Listener is invoked three times.
- The first two attempts throw exceptions.
- The third attempt succeeds.
- The record is not forwarded to the DLT.
- Offset is acknowledged per `AckMode` after successful processing.

This test proves retries work for recoverable errors. Do not use `Thread.sleep()` to wait for retry counts; use a latch, Awaitility, or polling with a timeout.

## 10. Testing That Records Move to the DLT After Retries Are Exhausted

For a listener that always throws a retryable exception, verify both the invocation count and the record on the DLT.

Create a test consumer to read the DLT:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

private Consumer<String, String> createDltConsumer(
        EmbeddedKafkaBroker broker,
        String groupId,
        String dltTopic) {

    Map<String, Object> properties =
        KafkaTestUtils.consumerProps(groupId, "false", broker);

    properties.put(
        ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
        "earliest"
    );

    var factory = new DefaultKafkaConsumerFactory<String, String>(
        properties,
        new StringDeserializer(),
        new StringDeserializer()
    );

    Consumer<String, String> consumer = factory.createConsumer();
    consumer.subscribe(List.of(dltTopic));
    consumer.poll(Duration.ofMillis(100));

    return consumer;
}
~~~

The test consumer uses a separate group ID and `auto.offset.reset=earliest` to read existing DLT records. In the test, call `createDltConsumer()` before sending the source record to avoid missing data.

The next test method is also placed inside `RetryAndDltIntegrationTest` from section 5. The test class needs to inject `EmbeddedKafkaBroker embeddedKafka` alongside `registry`, `kafkaTemplate`, and `probeListener`.

~~~java
@Test
void publishesRecordToDltAfterRetriesAreExhausted() throws Exception {
    var container = registry.getListenerContainer("permanentListener");
    ContainerTestUtils.waitForAssignment(container, 1);

    try (var dltConsumer = createDltConsumer(
            embeddedKafka,
            "permanent-dlt-test",
            "orders.permanent.DLT")) {

        kafkaTemplate.send(
            "orders.permanent",
            "permanent-001",
            "permanent-001"
        ).get(10, TimeUnit.SECONDS);

        ConsumerRecords<String, String> records =
            KafkaTestUtils.getRecords(
                dltConsumer,
                Duration.ofSeconds(10)
            );

        assertThat(probeListener.attemptsFor("permanent-001"))
            .isEqualTo(3);

        assertThat(records.count()).isEqualTo(1);

        var deadLetter = records.iterator().next();
        assertThat(deadLetter.key()).isEqualTo("permanent-001");
        assertThat(deadLetter.value()).isEqualTo("permanent-001");
    }
}
~~~

The example uses one source partition and DLT partition to preserve partition numbers. If the resolver preserves `record.partition()`, the DLT needs enough partitions matching all source partitions.

In real tests, you can use Awaitility to wait on counters or DLT records instead of relying on fixed poll timings. Ensure the DLT consumer has subscribed and completed assignment before sending records if the test needs exact delivery timing.

## 11. Inspecting DLT Headers and Source Metadata

The DLT must preserve enough information for operations teams to identify the original record. Spring Kafka adds dead-letter headers such as:

| Header | Information |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Source topic |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Source partition |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Source offset |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Processing consumer group |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Fully qualified exception class name |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message |

You can extend the DLT test to inspect the original topic header:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.kafka.support.KafkaHeaders;

var originalTopicHeader =
    deadLetter.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);

assertThat(originalTopicHeader).isNotNull();
assertThat(new String(
    originalTopicHeader.value(),
    StandardCharsets.UTF_8
)).isEqualTo("orders.permanent");
~~~

Actual headers depend on the Spring Kafka version and recoverer configuration. Use the `KafkaHeaders` constants of the active version rather than typing header names manually where possible. Do not rely on full stack traces in every environment because that header may be disabled or truncated to reduce record size and avoid exposing sensitive details.

Also verify the source partition and offset. Do not compare the DLT offset against the source offset as if they belonged to the same log; they are two independent topics.

## 12. Testing Non-Retryable Exceptions

A data error that cannot resolve itself after waiting should generally be classified as non-retryable. For example, `InvalidOrderPayloadException` registered via `addNotRetryableExceptions()`.

Tests must verify:

1. Listener is invoked exactly once.
2. No additional retries occur.
3. The record is published to the DLT.
4. Payload and source metadata are preserved.
5. Offsets are handled per recovery policy.

Do not make `IllegalArgumentException` or `NullPointerException` non-retryable mechanically. An exception might represent bad data in one module yet a programming error in another. Creating dedicated domain exceptions makes classification clearer.

Spring Kafka treats certain exceptions as fatal/non-retryable by default, especially deserialization or message conversion failures. When customizing classification, inspect the default configuration of your Spring Kafka version and override only with clear reason.

## 13. Testing When DLT Publishing Fails

A critical failure occurs when the recoverer cannot publish to the DLT due to a missing topic, missing partition, missing ACLs, broker outage, or incompatible serializer.

When using `recoverer.setFailIfSendResultIsError(true)`, DLT send failures are surfaced instead of being treated as successful recovery. Test this scenario in an isolated environment:

- Configure a destination resolver pointing to a nonexistent topic when the broker has auto-create disabled.
- Or use a test principal lacking `WRITE` permission on the DLT.
- Send a failing record to trigger recovery.
- Verify the error handler detects the DLT publish failure.
- Verify the source record is not marked recovered in a way that loses data.
- Observe the record being redelivered or retained according to `AckMode` and container configuration.

Exact offset behavior when the recoverer throws an exception depends on `AckMode`, container transactions, and Spring Kafka version. Therefore, tests must read committed offsets or observe redelivered records under the application's exact configuration rather than just asserting an exception in logs.

After granting permissions or fixing the topic, add a test proving the record can recover successfully without loss. Never leave a broken DLT destination in shared tests because it can cause the listener container to retry continuously and affect other tests.

## 14. Testing Deserialization Failures and DLT Payloads

Deserialization errors can occur during `poll()` before the listener is called. For a Spring Kafka error handler to handle them, `ErrorHandlingDeserializer` usually wraps the real deserializer.

A deserialization test should verify:

- Sending invalid bytes or malformed JSON to the source topic.
- Listener does not receive an invalid object.
- Error handler receives the deserialization error.
- Record is forwarded to the DLT per configured non-retryable or retry policy.
- DLT preserves raw key/value and required exception metadata.

Crucially, the DLT template must be able to serialize both normal payloads and raw byte arrays. If the template uses only `StringSerializer`, publishing a `byte[]` value may fail. Configure `DelegatingByTypeSerializer` to pick serializers by value type or use a dedicated recovery template.

Do not test only malformed JSON syntax. Also test incompatible schemas/versions, null tombstone values, and key deserialization failures if the system supports those cases.

## 15. Testing Non-Blocking Retries with `@RetryableTopic`

With non-blocking retries, records move through retry topics and are redelivered after delays. Example listener:

When retry topic infrastructure must be enabled explicitly, declare the following configuration (depending on application version and auto-configuration):

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.retrytopic.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
class RetryTopicTestConfiguration {
}
~~~

~~~java
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class NonBlockingRetryListener {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 200, multiplier = 2.0),
        retryTopicSuffix = ".retry",
        dltTopicSuffix = ".DLT"
    )
    @KafkaListener(
        topics = "orders.async",
        groupId = "orders-async-test"
    )
    public void handle(String message) {
        throw new IllegalStateException("Temporary downstream failure");
    }

    @DltHandler
    public void handleDlt(String message) {
        // Record that the message reached the DLT.
    }
}
~~~

Enable retry topic infrastructure with `@EnableKafkaRetryTopic` if your application config requires it; the Spring Boot/Spring Kafka version and annotation configuration determine activation. `attempts = "4"` is the expected total delivery count including the initial attempt and retries, unlike `FixedBackOff`'s retry count parameter.

Non-blocking retry tests should verify:

- Records route through retry topics per configured naming strategy.
- Delay between deliveries aligns with backoff within test tolerances.
- After exhausting attempts, the record lands in the DLT.
- The DLT handler receives the expected payload.
- Subsequent records on the source topic continue processing while an earlier record awaits retry.
- Keys, partitions, and required metadata are preserved per routing configuration.

Final retry topic names may include suffixes and delay values according to the naming strategy. Verify the active naming strategy and provision matching topics; do not hard-code default retry topic names from another version.

Non-blocking retry can alter record ordering. Tests must reflect business ordering requirements, especially when multiple events share a key or partition.

## 16. Testing Batch Listeners

If a listener processes batches, do not apply record listener expectations unchanged. When one item in a batch fails, retry behavior depends on the exception and identified record position.

With `DefaultErrorHandler`, a batch listener can throw `BatchListenerFailedException` to pinpoint the failing record in the batch. If the failing record is not identified, the container may retry the entire batch depending on configuration.

Batch tests should verify:

- Which batch is redelivered and how many times.
- Whether records processed successfully before the failure are reprocessed.
- Which offsets are committed.
- Whether the DLT contains only the failing record or the whole batch per recoverer strategy.
- Whether side effects for redelivered records are idempotent.

Do not write batch tests asserting only listener method invocation counts; inspect individual records and offsets because one invocation can contain multiple records.

## 17. Testing Offsets, Redelivery, and Idempotency

Retries and DLT relate directly to offsets. For record listeners, after the listener succeeds, the container commits offsets per `AckMode`. When a record is recovered and published to the DLT, the error handler may treat the record as handled per recovery policy and allow committing the corresponding offset.

One scenario to test is when a listener performs a side effect and the application stops before committing the offset. Kafka may redeliver the record after consumer restart or rebalance, causing the side effect to run again.

Therefore, tests should cover:

1. Listener records side effects keyed by event ID.
2. Simulate failure or stop the consumer before commit if the test harness allows it.
3. Restart the consumer with the same group ID.
4. Verify the record can be redelivered.
5. Verify deduplication or idempotency prevents duplicating side effects.

Do not use a new group ID for a redelivery test if the goal is to verify old committed offsets. A new group ID may start according to `auto.offset.reset`, skewing expected results.

For DLT, you can check committed offsets with `AdminClient.listConsumerGroupOffsets()` after the container finishes recovery. Wait for the offset to stabilize before asserting; do not read immediately after the DLT consumer receives the record because publishing to the DLT and committing the source offset are two separate operations to observe individually.

## 18. Synchronizing Tests Without Thread.sleep()

Kafka is asynchronous. A test can fail intermittently if it assumes a listener always finishes within a fixed time window.

Prefer:

- `ContainerTestUtils.waitForAssignment()` to wait until the listener has partition assignments.
- `CountDownLatch` when waiting for a specific listener action.
- Awaitility to wait for conditions such as retry counts, DLT records, or committed offsets.
- `KafkaTestUtils.getRecords(consumer, timeout)` to poll records with a time bound.
- `CompletableFuture.get(timeout, unit)` to wait for producer results.

Do not use `Thread.sleep(1000)` and assume the listener has finished processing. If needing to verify backoff, measure intervals between calls with generous tolerances; avoid asserting exact milliseconds since scheduling and broker latency fluctuate.

## 19. Test Scenario Matrix

| Scenario | Expected Outcome |
|---|---|
| Listener succeeds immediately | One invocation, no DLT |
| Transient error then success | Invocation count matches policy, no DLT |
| Persistent retryable error | Initial + retry count, then one DLT record |
| Non-retryable exception | No extra retries, forwarded to DLT |
| DLT topic missing partition | Observed recovery failure |
| DLT publish denied by ACL | Source record not treated as recovered successfully |
| Deserialization failure | Listener does not receive invalid object; DLT keeps raw data per config |
| Consumer restarts before commit | Redelivery possible; side effects remain idempotent |
| Batch listener fails mid-batch | Retries/commits exact records and offsets per strategy |
| Non-blocking retry | Record travels through retry topics and reaches DLT after attempts |
| Concurrent tests | Topics, groups, and message IDs do not collide |

## 20. Common Mistakes When Writing Tests

| Symptom | Cause | Fix |
|---|---|---|
| Test passes intermittently | Record sent before listener assignment completes | Await `waitForAssignment()` |
| No DLT record seen | Recoverer not attached to container factory or wrong DLT topic name | Check factory, resolver, and target topic |
| DLT consumer reads old records | Shared group ID or topic across tests | Use unique group IDs and isolated topics |
| More retries than expected | Confusing retry count with total attempts | With `FixedBackOff(interval, n)`, `n` is extra retries after initial attempt |
| DLT publish fails yet test passes | Recoverer send result not checked | Enable fail-on-send-error and assert recovery failure |
| DLT value deserialization fails | DLT serializer does not support raw `byte[]` or record type | Use a serializer compatible with all value types |
| Test does not prove offset commit | Checked DLT record only | Check committed offset via `AdminClient` or redelivery |
| False pass on TLS/SASL test | Embedded broker does not enable security | Use Testcontainers/staging with TLS/SASL/ACLs |
| Test affected by stale context | Listener container keeps running after test | Use `@DirtiesContext` and lifecycle cleanup |

## 21. Organizing Tests in CI

In CI, group tests by execution cost:

- Unit tests for exception classification and idempotency run fast on every commit.
- Embedded Kafka integration tests run on every pull request.
- Testcontainers brokers with TLS/SASL/ACLs run in security pipelines or nightly if startup cost is high.
- Staging smoke tests run after deployment and before receiving traffic.

Each test needs an overall timeout. If a test broker or consumer hangs, CI must stop with a clear error rather than tying up a worker indefinitely.

Do not share Kafka topics and consumer groups across different pipeline builds. Use build/test-run prefixes or isolated brokers so one test does not read another test's records.

## 22. Retry and Dead-Letter Testing Checklist

- [ ] Use `spring-kafka-test` or Testcontainers appropriate for the goal.
- [ ] Pre-create required source topics, retry topics, and DLTs.
- [ ] Attach the right `DefaultErrorHandler` to the listener container factory.
- [ ] Explicitly define retry count and total delivery count.
- [ ] Test transient failures followed by success.
- [ ] Test persistent retryable failures and verify the DLT.
- [ ] Test non-retryable exceptions.
- [ ] Inspect payload, key, topic, partition, offset, and DLT headers.
- [ ] Test DLT publish failure cases.
- [ ] Inspect raw `byte[]` when testing deserialization failures.
- [ ] Distinguish blocking retries from `@RetryableTopic`.
- [ ] Verify ordering and delays when using non-blocking retries.
- [ ] Test batch listeners separately if the application processes batches.
- [ ] Verify committed offsets and redelivery when needed.
- [ ] Isolate message IDs, topics, and group IDs per test.
- [ ] Wait for assignment and async conditions via latch/Awaitility/poll timeout.
- [ ] Do not use `Thread.sleep()` as the primary synchronization mechanism.
- [ ] Ensure side effects are idempotent when records are redelivered.

Testing retries and dead letters must verify the success path, the recovery path, and offset state. For blocking retries, verify `DefaultErrorHandler`, listener invocation count, and `DeadLetterPublishingRecoverer`. For non-blocking retries, verify routing through retry topics, delays, ordering, and DLT. By using a test broker with isolated topics/groups, waiting asynchronously with clear timeouts, and checking source metadata, development teams gain higher confidence in the recovery policies of their Spring Kafka applications.
