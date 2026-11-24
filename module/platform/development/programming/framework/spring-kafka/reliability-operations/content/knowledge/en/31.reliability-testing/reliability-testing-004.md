# Testing DLT Recovery

## Purpose of the test

In Spring Kafka, recovering to a Dead Letter Topic (DLT) is the step that handles a record after a listener fails and the retry policy is exhausted, or when an exception is classified as non-retryable. The test must prove that the failed record is routed to the right DLT, retains enough information for investigation, and that the consumer handles the offset according to its configuration.

A test that only verifies the listener threw an exception is not enough. It does not prove that the recoverer successfully published the record. Similarly, merely seeing a record in the DLT does not prove that the right number of retries occurred, source headers were preserved, or the source offset was handled properly.

For a typical non-transactional flow, the contract to verify includes:

1. The listener receives the record from the source topic.
2. The error handler executes the configured retry count and backoff.
3. After retries are exhausted, the recoverer publishes the record to the DLT.
4. The DLT record preserves the key, value, and required metadata of the original record.
5. DLT publish failures are detected and handled according to the chosen policy.
6. The source offset is acknowledged only according to the semantics of the container and acknowledgement mode in use.

## Distinguishing test layers

Do not use a single integration test to verify every detail. Separating tests by responsibility makes failures easier to pinpoint.

| Test layer | Components to test | What it can prove |
|---|---|---|
| Unit test | Exception classifier, BackOff, destination resolver, custom recoverer | Retry rules and topic/partition mapping are correct |
| Embedded Kafka integration test | Listener, DefaultErrorHandler, DeadLetterPublishingRecoverer, producer, and broker | The record is actually published to the DLT and has the expected headers |
| Testcontainers or broker test environment | Production-like broker config, replication, ACLs, quotas | Behavior with multiple brokers and infrastructure constraints |
| End-to-end test | Consumer group, offsets, DLT consumer, and replay workflow | The application's recovery flow works together with related components |

Embedded Kafka is well suited for testing the basic publish flow in CI. An embedded broker does not prove ISR behavior, replication factor, broker failover, or production ACLs. Those properties need to be tested against a broker with the corresponding configuration.

## Defining success conditions

Before writing the test, agree on the assertions:

- **Retry count:** total listener invocations equal the initial delivery plus the configured number of retries, if every attempt fails.
- **DLT destination:** the record arrives at the right topic and partition according to the destination resolver.
- **Payload:** the key and value are preserved, or transformed according to the defined contract.
- **Original metadata:** headers containing the source topic, partition, offset, and timestamp have valid values.
- **Exception metadata:** diagnostic headers reflect the exception that caused recovery, if the application enables these headers.
- **Send failure:** when publishing to the DLT fails, the recoverer must not silently treat the record as successfully stored if policy requires error detection.
- **Offset:** commit behavior matches the container's AckMode, transaction, and error handler.

Do not hard-code an assumption that every configuration commits offsets at the same point. For record listeners, batch listeners, manual acknowledgement, and transactions, the semantics differ. Tests must use the application's actual listener type and acknowledgement mode.

## Preparing Embedded Kafka

Add the Spring Kafka test dependency compatible with the application's Spring Kafka version:

~~~gradle
testImplementation("org.springframework.kafka:spring-kafka-test")
~~~

The following example uses Embedded Kafka with the source topic and DLT pre-created. Pre-creating the DLT in the test prevents auto topic creation from hiding topic or partition configuration errors.

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders", "orders.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class DltRecoveryIntegrationTest {
    // Test code shown in the following sections.
}
~~~

If using Maven, declare the spring-kafka-test artifact in test scope. Keep the dependency version aligned with Spring Kafka in the application; do not upgrade the test library alone to a different version.

In the test configuration, attach CommonErrorHandler to the listener container factory. Non-transactional example:

~~~java
@Bean
DefaultErrorHandler dltErrorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(template);

    // Propagate DLT send failures back to the error handler.
    recoverer.setFailIfSendResultIsError(true);

    // One initial delivery and at most one retry.
    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(0L, 1L)
    );
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
kafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory,
        DefaultErrorHandler dltErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(dltErrorHandler);
    return factory;
}
~~~

In the example, the second parameter of FixedBackOff is the number of retries after the initial delivery. Thus, a value of 1 means the listener can be invoked at most twice if both attempts fail. Verify the semantics and API of the Spring Kafka version in use before applying.

If the application already has its own listener container factory, configure the error handler on that factory. Do not create an additional test factory with a different name and accidentally leave the listener using the default production factory.

## Creating a deterministic listener

A test listener should have deterministic outcomes based on record contents. Avoid depending on external services or wall-clock time because those factors make tests hard to reproduce.

~~~java
@Component
class TestOrderListener {

    private final AtomicInteger attempts = new AtomicInteger();

    @KafkaListener(
        id = "orders-test-listener",
        topics = "orders",
        groupId = "orders-dlt-test"
    )
    void listen(ConsumerRecord<String, String> record) {
        attempts.incrementAndGet();

        if ("poison".equals(record.value())) {
            throw new IllegalArgumentException("invalid order");
        }
    }

    int attempts() {
        return attempts.get();
    }
}
~~~

With this listener, a record with value poison always fails. If BackOff allows one retry, the test expects two invocations before recovery. A valid record is processed successfully on the first attempt.

In real tests, reset counters between tests or create a separate context/bean per test. If tests run in parallel, use separate topics and groups so records or counters from one test do not affect another.

## Verifying the record is routed to the DLT

The basic test sends a poison record to the source topic, then reads the DLT with an independent consumer. The assertion consumer must use its own group, not the group of the listener under test.

~~~java
@Test
void publishesPoisonRecordToDlt() {
    Consumer<String, String> dltConsumer = createDltConsumer();

    embeddedKafka.consumeFromAnEmbeddedTopic(
        dltConsumer,
        "orders.DLT"
    );

    // Wait for the listener container to be assigned partitions before sending.
    ContainerTestUtils.waitForAssignment(
        listenerContainer,
        1
    );

    kafkaTemplate.send("orders", "order-42", "poison").join();

    ConsumerRecord<String, String> dltRecord =
        KafkaTestUtils.getSingleRecord(
            dltConsumer,
            "orders.DLT",
            Duration.ofSeconds(10)
        );

    assertThat(dltRecord.key()).isEqualTo("order-42");
    assertThat(dltRecord.value()).isEqualTo("poison");
    assertThat(listener.attempts()).isEqualTo(2);

    dltConsumer.close();
}
~~~

This is an illustrative structure; fields and helpers such as listenerContainer, embeddedKafka, kafkaTemplate, and listener are injected from the test context. Create the consumer with the appropriate deserializer and a separate group ID. With Spring Kafka test utilities, you can create consumer properties from EmbeddedKafkaBroker and set auto.offset.reset to earliest before creating the consumer.

If the listener container is managed by KafkaListenerEndpointRegistry, retrieve the container by listener ID to pass into waitForAssignment. The number of partitions to wait for must match the number of partitions assigned to the container in the test configuration.

Do not use Thread.sleep to guess that the listener has finished processing. Read the DLT with a finite timeout or use Awaitility to wait for an observable condition.

## Verifying DLT headers

DeadLetterPublishingRecoverer attaches metadata so operators know where a record came from and why it was recovered. Depending on the Spring Kafka version and header configuration, common headers include:

| Header | Content to verify |
|---|---|
| DLT original topic | Source topic name |
| DLT original partition | Source partition |
| DLT original offset | Offset of the source record |
| DLT original timestamp | Source timestamp when available |
| DLT exception FQCN | Fully qualified class name of the exception |
| DLT exception message | Exception message |
| DLT exception stacktrace | Stack trace if configured to retain this header |

Headers can be read using Spring Kafka's KafkaHeaders constants:

~~~java
Header originalTopic =
    dltRecord.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);

assertThat(originalTopic).isNotNull();
assertThat(new String(originalTopic.value(), StandardCharsets.UTF_8))
    .isEqualTo("orders");
~~~

Constant names and header types may differ by version. Use the constants from the project's version rather than hard-coding header strings in production code. Some metadata is serialized as a byte array, so tests need to decode it in the corresponding format.

Do not just check that a header exists. Verify the value against the actual topic, partition, and offset of the record that was sent. This helps catch partition mapping bugs or header issues when a record passes through multiple layers.

## Verifying retry count

Retry tests must distinguish the number of listener invocations from the number of retries. If the configuration allows R retries, the maximum total deliveries when always failing is:

~~~text
Total times the listener receives the record = 1 initial delivery + R retries
~~~

For example, with FixedBackOff(0L, 2L), the listener can receive the record up to three times before recovery. A backoff of 0 keeps tests fast; testing production configuration should also verify wait durations or the corresponding backoff strategy.

Another test should prove that a record that succeeds on retry does not enter the DLT:

~~~java
void succeedsOnSecondAttempt(ConsumerRecord<String, String> record) {
    int currentAttempt = attempts.incrementAndGet();

    if (currentAttempt == 1) {
        throw new IllegalStateException("temporary failure");
    }

    // Second attempt succeeds.
}
~~~

For this scenario, assertions should verify that the listener was called twice and no corresponding record appears in the DLT within a finite check window. Use a dedicated topic per test so the DLT does not contain records from previous tests.

## Verifying non-retryable exceptions

Some exceptions indicate invalid data that cannot be fixed by retrying. DefaultErrorHandler can be configured to route those exceptions straight to the DLT:

~~~java
DefaultErrorHandler errorHandler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

errorHandler.addNotRetryableExceptions(
    IllegalArgumentException.class
);
~~~

The test must prove that IllegalArgumentException results in only one listener invocation before recovery, while transient exceptions are retried according to BackOff.

Check both the root exception and wrapper exceptions. Some listeners or frameworks may wrap business errors in ListenerExecutionFailedException or another cause. The classification configuration must match the exception type that the error handler actually sees.

## Testing when DLT publishing fails

This is a case that needs its own test. Successful recovery and failed recovery have different operational implications.

If the producer cannot send to the DLT due to timeout, ACLs, missing topic, unavailable partition, or broker error, the system must surface the failure according to the chosen policy. With DeadLetterPublishingRecoverer, configuring failIfSendResultIsError allows send errors to be propagated instead of merely logging and treating recovery as complete.

This can be tested at two levels:

- **Recoverer unit test:** use a mocked KafkaOperations returning a failed send future, then verify that the recoverer raises an error when failIfSendResultIsError is enabled. Future APIs differ across Spring Kafka generations; newer versions use CompletableFuture, while older versions may use ListenableFuture.
- **Broker integration test:** configure the DLT producer without write permissions or send to an invalid destination in a secured test broker, then confirm the publish failure surfaces in the container/error handler and the record is not treated as successfully recovered.

When writing unit tests, check both failIfSendResultIsError enabled and disabled to confirm the error policy. In integration tests, avoid relying on a random broker error as the sole assertion; capture the specific exception and offset state to verify the failure took the intended branch.

Do not assume the listener will immediately be re-invoked when a DLT send fails. Subsequent behavior also depends on the error handler, BackOff, recoverer, AckMode, and transactions. Tests must reflect the application's actual policy.

## Verifying topic and partition mapping

If using the default destination resolver or a custom resolver, verify the target topic and partition with realistic data. For example, if the source topic orders has multiple partitions, the DLT needs enough partitions if the resolver preserves the source partition number.

A unit test for the resolver can verify:

- The target topic is constructed with the right suffix or routing rule.
- The target partition matches the source partition when required.
- Records with out-of-range partitions are handled according to the designed fallback.
- The resolver handles exceptions or records with special metadata properly.

Do not check only the topic name. A resolver that returns the right topic but the wrong partition can create hotspots, violate ordering, or send to a nonexistent partition.

## Verifying offsets and acknowledgements

After the recoverer successfully sends to the DLT, the container must handle the source offset according to configuration. This is easy to test incorrectly because commit behavior depends on many factors.

Clearly determine:

- Whether AckMode is RECORD, BATCH, MANUAL, or MANUAL_IMMEDIATE.
- Whether the listener is a record listener or a batch listener.
- Whether the consumer has auto commit enabled.
- Whether the error handler commits recovered records according to container configuration.
- Whether the flow uses Kafka transactions.
- Whether the offset is committed together with DLT publishing or as a separate step.

In the test, read the committed offset of the exact consumer group after the container finishes processing. Compare it against the test record's offset and the chosen commit rules. Use AdminClient or consumer group metadata appropriate for the Kafka client version.

Do not use a consumer assertion reading the DLT as the sole proof that the source offset was committed. Publishing to the DLT and committing the source offset are two separate outcomes that must be verified individually, especially in non-transactional flows.

## Testing when the application uses transactions

With Kafka transactions, recovery after rollback differs from a non-transactional error handler. Typically you need to configure DefaultAfterRollbackProcessor and an appropriate recoverer. When atomicity is required, publishing to the DLT and committing the source offset must be part of the transaction designed for the recovery flow.

A transactional test suite must prove at least:

1. The listener fails and the initial transaction rolls back.
2. Retries after rollback occur the expected number of times.
3. When retries are exhausted, the recoverer publishes to the DLT under the configured recovery transaction.
4. The DLT record appears only after the transaction commits.
5. The source offset is committed according to the transaction recovery policy.
6. When the transaction aborts, the DLT record does not appear as a committed result.

A test using only a single-broker Embedded Kafka is not sufficient to prove every transaction failure scenario of a production cluster. For high durability requirements, add tests on a multi-broker cluster with appropriate replication.

## Recommended test matrix

| Scenario | Expected outcome |
|---|---|
| Listener succeeds immediately | No DLT record; listener called once |
| Listener fails then succeeds | Retries the configured number of times; no DLT record |
| Listener fails until retries exhausted | One DLT record; listener receives the expected number of times |
| Non-retryable exception | Routed to DLT immediately; no retries executed |
| Missing DLT topic or invalid partition | Publish error detected; record not treated as successfully recovered |
| DLT producer lacks ACLs | Authorization error observed; source recovery follows error policy |
| Unserializable payload | Serializer error detected; required metadata not lost |
| Payload too large | RecordTooLarge detected and handled per policy |
| Custom destination resolver | Topic and partition follow rules |
| DLT publish succeeds but source offset not committed | Test detects incomplete state under chosen semantics |
| Transaction recovery commit | DLT record and offset committed consistently |
| Transaction recovery abort | No committed DLT record from aborted transaction |

Not every project needs the entire matrix on every CI run. Keep basic flow tests running regularly; broker security, replication, and fault injection tests can run in a dedicated integration pipeline.

## Reducing flaky tests

Kafka tests are asynchronous. A stable test must control partition assignment timing, record send timing, and DLT read timing.

- Wait for the listener container to be assigned partitions before sending records.
- Use a separate group ID for the consumer reading the DLT.
- Set auto.offset.reset to earliest when the test consumer needs to read records from the beginning of the topic.
- Create dedicated test topics or ensure topics are clean between tests.
- Use finite timeouts and Awaitility/KafkaTestUtils to wait for conditions.
- Avoid fixed Thread.sleep because processing times vary between developer machines and CI.
- Do not run tests in parallel if they share topics, group IDs, or AtomicInteger counters.
- Close consumers and AdminClient after the test completes.
- Set test timeouts long enough to capture meaningful failures without hanging the pipeline indefinitely.

If a test occasionally fails to find the DLT record, check whether the consumer subscribed before sending, whether offset reset is configured correctly, whether the listener container was assigned, and whether the DLT consumer is reusing an old group whose offset is at the end of the topic.

## Test failure reporting

When a recovery test fails, logs should include enough data to identify the failing step:

- Source topic, partition, offset, and record key.
- Consumer group and listener ID.
- Number of times the listener was invoked.
- Final exception and cause chain.
- DLT topic/partition chosen by the resolver.
- Producer send result and send exception if any.
- Relevant AckMode or transaction state.
- Source committed offset and observation timestamp.

Do not log sensitive payloads or full stack traces into DLT headers if data policies forbid it. Exception headers should be sufficient for diagnosis while maintaining appropriate size limits and retention.

## CI execution workflow

A practical pipeline can be organized in this order:

1. Run unit tests for retry policy, exception classification, and destination resolver.
2. Start Embedded Kafka and run integration tests for success, retry, recovery, and headers.
3. Run publish failure tests using mocked send futures or an ACL-enabled test broker.
4. Run transactional tests if the application enables Kafka transactions.
5. Run Testcontainers or a multi-broker Kafka environment on a schedule or in a dedicated integration pipeline.
6. Save test logs and broker information on failure so incidents can be reproduced.

When upgrading Spring Kafka or the Kafka client, re-run the DLT recovery test suite because APIs, future types, headers, and container configurations can change between versions.

## Operational conclusion

A reliable DLT recovery test suite must verify the full outcome of recovery: retry count, DLT topic/partition, payload, metadata, send failures, and source offsets. Integration tests with Embedded Kafka prove the basic flow; requirements around ACLs, replication, failover, and transactions need the corresponding test environments.

When tests are designed around these contracts, changes to error handlers, retry policies, serializers, or destination resolvers have clear evidence that failed records are retained and can be investigated and replayed under operational procedures.

