# Testing Consumer Retries in Spring Kafka

## 1. Testing goals

Consumer retry is the mechanism for reattempting processing of a Kafka record when a listener encounters a transient error. In Spring Kafka, retries can be performed directly inside the listener container using `DefaultErrorHandler` (blocking retry), or by routing records through scheduled retry topics with `@RetryableTopic` (non-blocking retry). Testing must prove that the retry policy behaves according to configuration and protects data when processing fails.

A consumer retry test suite should answer the following questions:

- Is the listener re-invoked when a retryable exception is thrown?
- Does the actual number of attempts match the configuration, and is the initial attempt counted toward the total?
- Does the consumer stop retrying once processing succeeds?
- Which exceptions are retried, and which are routed straight to the recoverer or DLT?
- After attempts are exhausted, is the record sent to the right DLT with the required source metadata preserved?
- Does the next record continue to be processed after the previous record is recovered?
- Do offsets, partitions, ordering, and duplicate handling meet business requirements?
- For non-blocking retries, does the record traverse the expected retry topics, delays, and DLT?

Tests must observe consumer and Kafka behavior. Merely checking that a method was called in a unit test does not prove that the listener container, error handler, DLT producer, and consumer group work together in practice.

## 2. Distinguishing the two retry mechanisms

### Blocking retry with `DefaultErrorHandler`

`DefaultErrorHandler` handles errors on the listener container thread. When the listener throws a retryable exception, the container performs retries according to `BackOff`. Once attempts are exhausted, the error handler invokes a recoverer, typically `DeadLetterPublishingRecoverer`, to send the record to the DLT.

Configuration example:

```java
@Configuration
public class KafkaRetryConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(KafkaTemplate<String, String> template) {
        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(template,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".DLT",
                                record.partition()));

        // 100 ms between retries; at most 2 retries after the initial invocation.
        return new DefaultErrorHandler(recoverer, new FixedBackOff(100L, 2L));
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            DefaultErrorHandler ordersErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, String> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
```

With `new FixedBackOff(100L, 2L)`, the listener has at most **3 invocations for the same record**: one initial delivery and two retries. The second parameter is the number of additional retries, not the total invocation count. Verify this clearly in tests to avoid misconfigured policies or miscounted alerts.

### Non-blocking retry with `@RetryableTopic`

`@RetryableTopic` forwards records to retry topics instead of blocking the consumer thread while waiting to retry. After the configured number of attempts, the record is sent to the DLT. Retry topics may be auto-created or pre-provisioned depending on deployment configuration.

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 100, multiplier = 2.0),
        dltTopicSuffix = "-dlt")
@KafkaListener(topics = "orders.nonblocking", groupId = "orders-retry-it")
public void consume(OrderEvent event) {
    orderService.process(event);
}

@DltHandler
public void handleDlt(OrderEvent event) {
    // Log or route to final failure handling workflow.
}
```

In this configuration, `attempts = "4"` represents the total number of attempts, including the initial processing attempt. Verify this counting behavior in the Spring Kafka version in use. Retry topic names, DLT names, and partition counts depend on suffixes, the topic naming strategy, and actual configuration.

| Characteristic | Blocking retry | Non-blocking retry |
|---|---|---|
| How retries run | Re-invokes the listener on the container thread | Publishes the record to retry topics |
| Common configuration | `DefaultErrorHandler`, `BackOff`, recoverer | `@RetryableTopic`, `@Backoff`, DLT handler |
| Attempt counting | `FixedBackOff` specifies additional retries after the first attempt | `attempts` specifies total attempts |
| Impact on consumer | A failing record can block processing during backoff | The original consumer can continue processing other records |
| Ordering | Blocking retries can hold the affected partition during error handling | Ordering across records may change due to separate topics and delays |
| What to verify | Invocation count, backoff, recovery, and offsets | Routing through retry topics, wait times, total attempts, and DLT |

Do not apply the same expectations for attempt counts or ordering to both mechanisms. Before writing tests, determine which mechanism the listener uses and the exact Spring Kafka version.

## 3. Choosing test levels

### Unit tests for error classification logic

Unit tests are well suited for pure application logic, such as:

- Classifying transient vs. unrecoverable exceptions.
- Deciding whether to retry a given failure type.
- Computing delays in a custom `BackOff`.
- Building idempotency keys or business decisions when receiving the same event again.

Unit tests do not require starting a Kafka broker. You can mock services or dependencies and assert classification logic. Do not use mocks to replace all of `DefaultErrorHandler` or `@RetryableTopic` and conclude that retry integration works.

### Integration tests with Embedded Kafka

Embedded Kafka is well suited for testing Spring Kafka flows within a single test context:

- The producer sends a record to the test topic.
- The listener container receives the record and invokes the listener.
- The error handler executes retries per configuration.
- The recoverer sends the record to the DLT.
- A test consumer reads the DLT and verifies the key, value, partition, and required headers.

An embedded broker keeps tests self-contained, fast, and independent of a shared Kafka cluster. It is still a real Kafka broker running inside the test process, though it does not replace production infrastructure tests such as ACLs, TLS, quotas, or custom broker settings.

### Integration tests with Testcontainers

Choose Testcontainers when you need to test against a Kafka version or broker configuration closer to the deployment environment, or when verifying behavior related to the broker image, listener endpoints, and container configuration. Testcontainers requires a Docker runtime and is typically slower than Embedded Kafka.

### Testing in deployment-like environments

Some behaviors can only be fully verified in production-like environments: ACLs, SASL/TLS, schema registry, broker quotas, network policies, real partition counts, and load handling. Run controlled tests with dedicated topics and consumer groups, never against topics or groups serving live traffic.

## 4. Preparing test dependencies

For Spring Boot projects using Gradle, add Spring Kafka test support to the test configuration. Use Spring Boot dependency management/BOM to select versions compatible with Spring Kafka in the application.

```groovy
dependencies {
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}
```

`spring-kafka-test` provides `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `KafkaTestUtils`, and Kafka test helpers. Awaitility waits for an asynchronous condition to be met without hard-coding a fixed `Thread.sleep`.

Some test utility APIs change across Spring Kafka versions. When upgrading versions, check the API of the actual dependency, especially how bootstrap servers are configured for Embedded Kafka, how consumers are polled, and how single records are fetched.

## 5. Creating a controllable listener in integration tests

Tests need a deterministic way to trigger failures. Avoid depending on a real database or external API just to make the listener fail. You can use a thread-safe probe in the test context to specify how many times a record should fail before succeeding.

Listener example:

```java
@Component
public class RetryProbe {

    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger failuresBeforeSuccess = new AtomicInteger();

    public void failForNextRecord(int failures) {
        attempts.set(0);
        failuresBeforeSuccess.set(failures);
    }

    public int attempts() {
        return attempts.get();
    }

    @KafkaListener(
            id = "orders-retry-listener",
            topics = "${app.kafka.orders-topic}",
            groupId = "orders-retry-it")
    public void listen(ConsumerRecord<String, String> record) {
        int currentAttempt = attempts.incrementAndGet();
        if (currentAttempt <= failuresBeforeSuccess.get()) {
            throw new IllegalStateException("simulated transient failure");
        }
    }
}
```

This probe is intentionally simple to illustrate retrying a single record in one test. If a test handles multiple concurrent records, count per key or correlation ID instead of using a single shared counter. Do not run tests in parallel on the same listener state if they can overwrite each other's failure counts.

In real applications, the listener typically calls a business service. You can replace that dependency with a test double to control failure counts while keeping the real listener container and error handler.

## 6. Testing blocking retry with Embedded Kafka

### Test broker configuration

Declare the source topic and DLT topic in the test. The example below uses a single partition to keep original-partition routing verification simple:

```java
@SpringBootTest(properties = {
        "app.kafka.orders-topic=orders",
        "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders", "orders.DLT"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class BlockingRetryIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    RetryProbe retryProbe;

    // Tests are presented in the following sections.
}
```

Ensure test producers and consumers use `StringSerializer`/`StringDeserializer`, and that the test listener factory actually has `DefaultErrorHandler` attached. Across Spring Kafka versions, `@EmbeddedKafka` supports different bootstrap server properties; use the property supported by the installed version.

### Testing retry success before attempts are exhausted

Suppose the listener fails twice and succeeds on the third attempt, with `FixedBackOff(100L, 2L)`. The test must confirm the listener is invoked three times and the record is not routed to the DLT.

```java
@Test
void retriesUntilListenerSucceeds() throws Exception {
    retryProbe.failForNextRecord(2);

    kafkaTemplate.send("orders", "order-42", "payload")
            .get(10, TimeUnit.SECONDS);

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
            assertThat(retryProbe.attempts()).isEqualTo(3));
}
```

Completing the producer send only confirms that the producer received the send outcome per configuration; it does not mean the listener has processed the record. Therefore, the test waits for the listener counter to reach the expected value. In a complete test, add a per-key success signal or record the result from the service to prove the final attempt finished.

### Testing routing to the DLT after retries are exhausted

When the listener always fails, `DefaultErrorHandler` must invoke the recoverer after the initial attempt and two retries. The test must read the record from the DLT while also verifying the listener invocation count.

```java
@Test
void publishesRecordToDltAfterRetriesAreExhausted() throws Exception {
    retryProbe.failForNextRecord(Integer.MAX_VALUE);

    Map<String, Object> consumerProps = KafkaTestUtils.consumerProps(
            "dlt-assert-" + UUID.randomUUID(), "false", embeddedKafka);
    consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    try (Consumer<String, String> dltConsumer =
                 new DefaultKafkaConsumerFactory<String, String>(
                         consumerProps,
                         new StringDeserializer(),
                         new StringDeserializer()).createConsumer()) {

        embeddedKafka.consumeFromAnEmbeddedTopic(dltConsumer, "orders.DLT");

        kafkaTemplate.send("orders", "order-99", "bad-payload")
                .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> dltRecord = await()
                .atMost(Duration.ofSeconds(15))
                .until(() -> {
                    ConsumerRecords<String, String> records =
                            dltConsumer.poll(Duration.ofMillis(250));
                    return records.isEmpty() ? null : records.iterator().next();
                }, Objects::nonNull);

        assertThat(retryProbe.attempts()).isEqualTo(3);
        assertThat(dltRecord.key()).isEqualTo("order-99");
        assertThat(dltRecord.value()).isEqualTo("bad-payload");
        assertThat(dltRecord.topic()).isEqualTo("orders.DLT");
    }
}
```

Typical imports include `Consumer`, `ConsumerRecord`, `ConsumerRecords`, `ConsumerConfig`, `DefaultKafkaConsumerFactory`, `StringDeserializer`, `KafkaTestUtils`, `Duration`, `UUID`, `Objects`, and Awaitility. Adjust generic types and the `createConsumer()` API to match the project's Spring Kafka version.

The test consumer must subscribe/assign the DLT before sending the record to avoid missing messages in test configurations that do not read from the beginning. `consumeFromAnEmbeddedTopic` typically assigns partitions and seeks according to the utility's policy; verify your version's behavior if a test needs to read from a specific offset.

In real tests, also verify DLT headers if the application relies on source metadata:

```java
assertThat(dltRecord.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC))
        .isNotNull();
assertThat(dltRecord.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET))
        .isNotNull();
```

Exact headers depend on the Spring Kafka version, recoverer, and header configuration. Verify the header names and values in real messages. If using a custom destination resolver, verify that the target topic and partition match the application's routing rules.

### What to avoid in the example

Do not use a `Thread.sleep(5000)` and assume retries have finished. Processing time depends on the broker, scheduler, and test process load. Waiting on observable conditions such as counters, records in the DLT, or business outcomes makes tests much more stable. Also avoid asserting an exact millisecond interval for each retry; the scheduler and operating system introduce variance.

## 7. Testing exception classification

Not every exception should be retried. For example, transient timeout errors can be retried, whereas validation errors from malformed payloads usually will not change if the same record is redelivered.

With `DefaultErrorHandler`, non-retryable exceptions can be configured via `addNotRetryableExceptions(...)` or classified via `setClassifications(...)`, depending on requirements and version. Tests should verify each branch separately:

| Scenario | Expected behavior |
|---|---|
| Transient exception, subsequent attempt succeeds | Listener is re-invoked the required number of times; record is processed successfully |
| Transient exception, always fails | Retries the configured number of times; then invokes recoverer or DLT |
| Non-retryable exception | Configured retries are not executed; routed to recovery per policy |
| Exception wrapped in another exception | Classified accurately per cause chain or configured classifier |
| Recoverer handles successfully | Record is recovered per policy; consumer proceeds to the next record |

Example declaring a non-retryable exception:

```java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(100L, 2L));

errorHandler.addNotRetryableExceptions(IllegalArgumentException.class);
```

The test for `IllegalArgumentException` must verify the listener is invoked only once before recovery. The test for other exceptions must verify invocation count matches `BackOff`. If the application uses a custom exception classifier, test subclasses and nested causes directly to prevent misclassification.

Do not mark overly broad exceptions like `RuntimeException` as non-retryable if the application has transient errors inheriting from that type. Conversely, do not retry validation errors endlessly or too many times simply because all errors pass through one catch block.

## 8. Testing non-blocking retry with `@RetryableTopic`

Non-blocking retries must be tested across the intermediate topics. Tests must prove that records are re-sent on schedule, reach the DLT after the total number of attempts, and are not unexpectedly duplicated.

### Identifying topics to test

Retry topic names depend on the `@RetryableTopic` configuration, suffixes, topic naming strategy, and Spring Kafka version. Before testing, identify the actual list of topics created from the configuration. Topics can be provisioned with `@EmbeddedKafka(topics = {...})` or an allowed topic creation mechanism in tests. Do not hard-code guessed topic names from an example and reuse them across every version.

For a retry configuration with multiple delays, determine the number of retry topics created, partition counts, replication factors, and the DLT topic. When using a test broker with auto topic creation, still verify that the topics actually exist and have partition counts matching the source topic.

### Scenarios to test

1. Send a record to the source topic.
2. Make the listener fail on initial attempts and succeed on a later attempt.
3. Verify the record appears on the configured retry topic and is eventually processed successfully.
4. For the always-failing case, verify total attempts match `attempts` and the record ultimately arrives in the DLT.
5. Verify key, payload, correlation ID, original topic/partition/offset, and required headers are preserved across topic hops.
6. Verify the `@DltHandler` or DLT consumer receives the expected record without causing unintended business side effects.

You can use `@DltHandler` to verify the final destination, or a separate test consumer reading the DLT. If the DLT handler writes to a database or calls another service, verify side effects with a test double or reconcilable test data.

### Verifying backoff timing

Backoff is the minimum wait time per policy; actual delivery times may be later due to scheduling, broker overhead, and load. Tests should verify the record does not appear before a reasonable lower bound if that matters, then wait for it to appear within a generous timeout. Avoid requiring a retry to happen at an exact millisecond N.

For exponential backoff, verify the configured delay tiers with a test that allows enough time and inspect timestamps/headers if recorded by the system. Do not force the test suite to wait several minutes just to verify a formula; use shorter test-specific delays while keeping the backoff logic intact.

## 9. Testing offsets, partitions, and ordering

Retrying is not just counting listener invocations. It affects when offsets are committed and processing order.

### Offsets and recovery

Test these scenarios:

- Record succeeds after retry: offset advances per ack mode and container configuration.
- Record is recovered to the DLT: recovery is acknowledged per configuration; consumer does not loop endlessly on the same record.
- DLT publish fails: the error handler reacts per configuration, and does not mark the record recovered if the send was not confirmed per reliability requirements.
- Application restarts mid-retry: redelivery and duplicate processing can occur; business logic must be safe when receiving the record again.

Do not assume every Spring Kafka configuration commits offsets in the same way. Ack mode, record/batch listener, transactions, error handler, and library version can change details. Write tests around the behavior the application commits to, then verify offsets via the consumer group or an independent test consumer.

### Partitions and keys

If the recoverer sends to the DLT on the same partition number as the source record, the destination topic must have enough matching partitions. Test with multiple partitions to ensure the destination resolver does not target an out-of-range partition. If the application intentionally redistributes by key, verify the new partition mapping and its impact on ordering.

Do not use a single partition to conclude that a multi-partition system works correctly. A simple single-partition test can verify retry counts; a separate test should verify partition mapping, keys, and source metadata.

### Ordering

Blocking retries can cause a failing record to hold up the partition's processing thread while waiting to retry. Non-blocking retries move the record to another topic, so subsequent records on the source topic may be processed before the record awaiting retry. If business rules require per-key ordering, tests must send multiple records with the same key and verify behavior matches the design.

If ordering is not guaranteed by the retry architecture, the application needs version/event sequence checks, state transition guards, or another mechanism to reject out-of-order events. Do not infer ordering solely from records sharing the same Kafka key.

## 10. Testing idempotency and side effects

Kafka consumers can often receive a record again, such as when a listener writes to an external system and the process stops before the offset is committed. In-process retries can also re-invoke the listener after part of the logic ran before throwing an exception.

An idempotency test should simulate this scenario:

1. The listener receives an event and executes the first side effect.
2. An error occurs after the side effect but before processing finishes.
3. The consumer retries or redelivers the record after a restart.
4. The system guarantees the same event does not produce duplicate side effects, or has a defined compensation mechanism.

Common techniques include idempotency keys, database unique constraints, inbox/deduplication tables, appropriate business transactions, or event version checks. Tests must verify the final business outcome, not just listener invocation counts.

For example, a business assertion might verify that an order transitions state only once even if the listener is invoked multiple times. If each attempt is allowed to create an audit entry, tests must distinguish attempt logs from committed business transactions.

## 11. Testing the DLT and metadata

Once a record exhausts retries, the DLT is evidence that the system retained the message for investigation or later reprocessing. Tests should confirm:

- The record is sent to the right DLT for the source topic/listener.
- Key and payload remain intact, unless the application has a defined transformation.
- Original topic, partition, offset, timestamp, and consumer group are preserved in headers if supported by the recoverer.
- Exception class, exception message, and stack trace are stored per configuration and security policy.
- Records are not misrouted to another listener's DLT.
- The DLT consumer or `@DltHandler` receives the record and handles it per contract.

Do not write sensitive payloads or stack traces containing secrets into widely shared test report logs. If headers include exception messages or stack traces, verify that sensitive data is scrubbed per system requirements.

If the application uses a customized `DeadLetterPublishingRecoverer`, test both the topic/partition resolver and how publish outcomes are handled. A test that only asserts the recoverer method was called does not prove the record actually exists in the DLT.

## 12. Testing DLT publish failures

The DLT write path can also fail due to a missing topic, ACLs, broker issues, timeouts, or producer errors. This is critical because the consumer may not be allowed to consider the record recovered if the message was not safely persisted.

Scenarios that should have dedicated tests:

- Recoverer sends successfully: record appears in the DLT and the consumer flow continues per policy.
- Producer fails to send to DLT: failure is observed and handled per error handler/container configuration.
- Missing DLT topic or invalid partition: test confirms the failure is detected rather than silently dropping the record.
- Producer callback/send result reports an error: confirm the recoverer's send verification matches application requirements.

Do not simulate broker failure by shutting down a broker shared across the test suite. You can use a producer test double to test error branches in custom code, or an isolated broker environment to test real publish failures. Clearly distinguish unit tests of error branches from integration tests of Kafka behavior.

## 13. Testing deserialization and pre-listener errors

Not all errors originate inside the `@KafkaListener` method. Deserializers can fail before the listener ever receives the payload. Therefore, a counter inside the listener is insufficient for testing retries of deserialization failures.

If the application uses `ErrorHandlingDeserializer`, tests should send malformed payloads or incompatible schemas and verify that the error handler/recoverer receives the record per configuration. Verify whether headers containing exception and raw data details match policy. For JSON, test malformed JSON, missing required fields, wrong types, and unsupported schema versions.

For deserialization errors, verify specifically how the framework passes the exception and raw record to the error handler in the version in use. Do not assume the listener will be invoked once per deserialization failure.

## 14. Making tests stable and easy to diagnose

### Avoiding race conditions

- Create a dedicated consumer group per test or per test class.
- Use dedicated topics or ensure tests do not run concurrently on the same topic and group.
- Create the test consumer and subscribe to the DLT before sending the record.
- Wait on specific conditions using Awaitility, `CountDownLatch`, or bounded polling.
- Use thread-safe counters/maps when the listener runs on another thread.
- Reset state before each test; do not share counters across tests running in parallel.
- Set finite timeouts so tests fail clearly instead of hanging.

### Avoiding unnecessary time dependencies

Do not use long `Thread.sleep` calls to guess that the consumer has finished retrying. If backoff needs verification, record attempt timestamps or observe when records arrive. Allow reasonable scheduling jitter and do not assert exact milliseconds.

### Isolating data

Each test should use unique keys and identifiable payloads. If tests run against a shared broker, include a run ID in topic/group or resource names, and establish safe resource cleanup procedures. Do not delete topics or groups used by other tests or services.

### Collecting evidence when a test fails

When a test times out, capture:

- Listener container ID and running state.
- Consumer group, members, partition assignments, and lag.
- Listener invocation counts per key.
- Whether source, retry, and DLT topics exist.
- Producer send result and last exception.
- Headers of the received record.

This information helps distinguish whether the test failed to send the record, the listener was not assigned partitions, retries had not finished backoff, or the recoverer failed to send to the DLT.

## 15. Recommended test scenario matrix

| Group | Scenario | Key assertion |
|---|---|---|
| Basic retry | Fails once then succeeds | Listener is re-invoked; record completes only after the successful attempt |
| Retry limit | Always fails | Invocation count matches policy; recovery occurs after final attempt |
| Exception classification | Non-retryable error | No unnecessary retries; record follows defined recovery branch |
| Backoff | Fixed or exponential | Ordering and wait intervals align with configuration within tolerance |
| DLT | Retries exhausted | Record appears in the right DLT, preserving key/value and required metadata |
| DLT publish failure | Broker/topic/producer returns error | Does not silently treat record as recovered; error is observed |
| Continued processing | Record A fails, record B is valid | Record B is processed according to listener and partition semantics |
| Offsets | Retry/recovery/restart | Offsets and redelivery match ack mode, transactions, and error handler |
| Partitions | Multiple partitions | DLT routing and partition mapping are correct |
| Ordering | Multiple records with same key | Ordering behavior matches business contract |
| Idempotency | Side effect occurs before exception | Retries do not create duplicate business side effects |
| Non-blocking | Via retry topics | Topics, attempts, delays, and DLT match configuration |
| Deserialization | Invalid payload | Pre-listener error is handled per deserializer/error handler configuration |
| Restart | Consumer stops mid-retry | Redelivery and business outcomes are safe and reconcilable |

Not every project needs every scenario in one test suite. Select cases based on the retry mechanism, data semantics, ordering requirements, dependencies, and criticality of the business flow.

## 16. Running tests and troubleshooting common errors

With Gradle, run a specific test class:

```bash
./gradlew test --tests "com.example.kafka.BlockingRetryIntegrationTest"
```

On Windows, `gradlew.bat` can be used instead of `./gradlew`. If the project defines a separate integration test source set or task, use the task configured in the project build.

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Test producer sends successfully but listener counter is 0 | Listener not started, wrong topic/group, partitions not assigned yet | Container registry, bootstrap servers, topic, group, and consumer logs |
| Counter higher than expected | Test sent duplicates, listener read old records, multiple instances share state, or retry config differs from expected | Unique keys, separate group, offset reset, retry count, and concurrency |
| DLT has no record | Recoverer not invoked, publish failed, wrong topic/partition, or test consumer subscribed too late | Last exception, producer send result, topic metadata, and subscribe timing |
| Flaky test (passes sometimes, fails sometimes) | Race condition, timeout too short, shared state, or sleep dependency | Awaitility, separate consumer group, proper timeouts, and thread-safe state |
| DLT record has invalid partition | Target topic has fewer partitions than source or resolver chooses wrong partition | Destination resolver and topic partition count |
| Non-blocking retry never reaches DLT | Wrong attempts, retry topic not created, retry topic listener not running, or exception classified differently | Topic topology, retry config, group, and exception classifier |
| Record processed twice | Non-idempotent side effect, uncommitted offset, or replay/redelivery | Idempotency key, transactions, ack mode, and recovery flow |

If a test fails, do not immediately increase timeouts or retry counts to make it pass. First determine whether the consumer received the record, how many times the listener was invoked, and whether the recoverer published successfully.

## 17. Consumer retry test completion criteria

A retry change should be considered verified only when all assertions tied to the application's contract pass:

- Attempt counts and counting semantics match the blocking or non-blocking mechanism in use.
- Retryable and non-retryable exceptions are classified accurately.
- Records that succeed after retry are not mistakenly routed to the DLT.
- Records that exhaust attempts are recovered or routed to the right DLT.
- Required source metadata and error details are preserved per configuration.
- The consumer stays healthy and processes subsequent records per defined semantics.
- Offsets, partitions, ordering, and idempotency are verified at a level appropriate for business needs.
- Asynchronous tests have explicit timeouts, thread-safe state, and no dependency on shared brokers.
- Limitations due to the Spring Kafka version or test broker are documented so maintainers understand the scope of evidence.

## 18. Pull request checklist

- [ ] Tests clearly state whether blocking retry or non-blocking retry is being verified.
- [ ] Attempt counts are calculated accurately, including the initial attempt and additional retries where applicable.
- [ ] Both retry-success and retries-exhausted cases are covered.
- [ ] Non-retryable exceptions are tested if the application classifies exceptions.
- [ ] Verified that the record actually appears in the DLT, not merely that the recoverer was called.
- [ ] Verified key, payload, partition, and important headers.
- [ ] Evaluated offsets, ordering, and idempotency against business requirements.
- [ ] Tests use isolated topics/groups, bounded asynchronous waits, and avoid fixed sleeps.
- [ ] Test configuration is compatible with the project's Spring Kafka/Kafka versions.
- [ ] Test results and environmental limitations are clearly documented in the pull request.
