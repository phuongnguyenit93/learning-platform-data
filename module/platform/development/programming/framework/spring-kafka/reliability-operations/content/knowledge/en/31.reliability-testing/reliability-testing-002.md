# Testing Producer Send Failures

## Goals and scope

Testing producer send failures proves that the application detects errors when sending records to Kafka, propagates failures to the appropriate handling layer, applies bounded retries when suitable, and does not report success when the broker has not acknowledged the send. A reliable test must distinguish between errors thrown synchronously inside the `send()` call, errors returned asynchronously via a future/callback, and errors that only appear when committing a transaction.

This content focuses on Spring for Apache Kafka with `KafkaTemplate`, `ProducerFactory`, and the Kafka producer client. The main examples use Spring Kafka 3.x, Java 17+, JUnit 5, Mockito, and AssertJ. Starting in Spring Kafka 3.0, `KafkaTemplate.send(...)` methods return `CompletableFuture<SendResult<K,V>>`. Older versions use `ListenableFuture`; check the version compatibility section before applying the test code.

Testing goals:

- Distinguish producer creation errors, serialization errors, producer invocation errors, and errors returned by the broker after sending.
- Confirm that the future completes successfully or fails in accordance with the send result.
- Verify that the application records errors, emits appropriate metrics/logs, and does not swallow exceptions.
- Confirm bounded retries for the right exception types without creating unwanted duplicates.
- Verify timeouts, transaction abort/commit, and behavior when the broker or network is unavailable.
- Keep tests stable, with finite wait deadlines and without relying on arbitrary sleeps.

## 1. Error model of a producer send

A send through `KafkaTemplate` goes through multiple stages. Where the error occurs determines whether an exception is thrown immediately or completes the future exceptionally.

~~~text
Application
   |
   | KafkaTemplate.send(...)
   v
Build ProducerRecord / acquire Producer from ProducerFactory
   |
   +---- local failure: configuration, serializer, producer creation,
   |     metadata/buffer wait exceeded
   |        -> may throw synchronous exception
   |
   v
KafkaProducer.send(record, callback)
   |
   +---- send failure / broker rejection / network / timeout
   |        -> callback receives exception
   |        -> CompletableFuture completes exceptionally
   |
   v
Broker acknowledges per acks configuration
   |
   +---- success -> SendResult and RecordMetadata
   |
   +---- uncommitted transaction -> send result is not yet commit result
~~~

Common failure categories:

| Category | Examples | Typical observation |
|---|---|---|
| Input errors | Empty topic, invalid key/value, malformed headers | Can occur immediately when building the record or calling send |
| Serializer errors | Invalid schema, serializer throws an exception, payload cannot be encoded | Can occur synchronously or during producer send processing |
| Producer initialization errors | Misconfiguration, invalid authentication/TLS, unable to create producer | Can throw an exception before a future is returned |
| Metadata/buffer errors | Unable to fetch metadata, producer buffer full and waits beyond `max.block.ms` | The send call may block and then throw an exception |
| Broker rejections | Authorization, record too large, invalid topic/partition | Usually surfaced as an asynchronous error via callback/future |
| Network errors | Broker disconnected, request timeout, leader change | Client may retry internally before reporting the final error |
| Delivery timeout | Unable to deliver record within `delivery.timeout.ms` | Future fails after the client's delivery deadline expires |
| Transaction | Sent within a transaction but commit/abort fails | Individual send may succeed while the transaction still fails to commit |

Do not assume all exceptions surface the same way. Specific behavior depends on the Kafka client version, Spring Kafka version, serializer, producer configuration, and timing of the error.

### 1.1. Synchronous vs. asynchronous errors

**Synchronous errors** occur before the producer can accept the record for sending, or while acquiring the producer, metadata, or buffer space. For example: `ProducerFactory.createProducer()` throws an error, serializer configuration is invalid, or the producer cannot fetch metadata within the wait limit. In this case, the `KafkaTemplate.send()` call itself can throw an exception before returning a future.

**Asynchronous errors** occur after the send command has been accepted into the producer's processing pipeline. For example, the broker rejects the record, the network fails to recover, or the delivery timeout expires. The application receives the error via callback and the `KafkaTemplate` future completes exceptionally.

With Spring Kafka 3.x, both paths must be handled. Calling only `future.get()` cannot catch an exception thrown before the future variable is assigned. Conversely, wrapping only the `send()` call in try/catch misses asynchronous errors if the application does not observe the future.

### 1.2. Meaning of a send result

`SendResult<K,V>` contains the sent record and `RecordMetadata` when the producer receives a successful acknowledgement according to the `acks` configuration. Metadata provides the topic, partition, offset, and timestamp reported by the broker.

A successful send result does not automatically prove that a consumer has processed the record or that downstream business processing is complete. When sending inside a transaction, a send result also does not prove that the transaction has committed. Tests must clearly define the success criteria for the component under test.

## 2. Preparing the test environment

### 2.1. Test dependencies

Common Maven dependencies example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If the project does not use Spring Boot dependency management, declare compatible versions for Spring Kafka, Kafka client, JUnit, Mockito, and AssertJ. Avoid forcing a Kafka client version different from the one managed by Spring Kafka without verifying compatibility.

### 2.2. Choosing the right type of test

| Test type | Real components | Used to verify |
|---|---|---|
| Service unit test | Mock `KafkaTemplate` | How the application reacts to a failed future or synchronous exception |
| `KafkaTemplate` test with `MockProducer` | Real `KafkaTemplate`, mock producer | Callbacks, futures, metadata, and error paths of the template |
| Integration test with broker | Real Kafka broker in test | Serializers, client configuration, topics, ACLs, and real round-trip |
| Fault-injection test | Real broker plus proxy/fault injector | Network partitions, broker disconnects, timeouts, and recovery |

Each layer answers a different question. Unit tests do not prove that the Kafka client handles network failures properly; a passing integration test also does not prove that the service does not swallow errors. Combine layers according to the application's risk profile.

## 3. Designing components for testability

A publisher should return the asynchronous result to its caller or forward errors to an observable handling mechanism. Do not discard the future if the send outcome affects business logic.

~~~java
@Service
public class OrderPublisher {

    private static final String TOPIC = "orders";

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
~~~

If the component needs to log or update metrics, attach a callback while preserving the failure state of the future:

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publish(
        OrderEvent event) {
    return kafkaTemplate.send(TOPIC, event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception == null) {
                    // Increment send success metric; do not log sensitive payloads.
                    sendSuccessCounter.increment();
                }
                else {
                    // Record error and minimal context for investigation.
                    sendFailureCounter.increment();
                    log.warn("Could not publish order event, orderId={}",
                            event.orderId(), exception);
                }
            });
}
~~~

`whenComplete` preserves the success/failure outcome of the source stage if the callback completes normally. If the callback itself throws an exception, the returned stage can also fail due to the callback error. Do not use `exceptionally(ex -> null)` just to turn the future into a success; that hides send failures.

If a business API requires a uniform contract where all errors are represented as failed futures, synchronous exceptions can be converted into failed futures:

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publishSafely(
        OrderEvent event) {
    try {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
    catch (RuntimeException exception) {
        return CompletableFuture.failedFuture(exception);
    }
}
~~~

Apply this approach only when callers are designed to observe the future. Do not catch `Throwable`, do not turn errors into successful results, and do not suppress configuration errors that should fail fast at startup.

## 4. Unit testing services with a mocked KafkaTemplate

Unit tests focus on application behavior: passing the right topic/key/value, propagating send errors back to the caller, and not marking operations successful when the future fails.

### 4.1. Testing asynchronous failures

Example using JUnit 5, Mockito, and AssertJ:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @InjectMocks
    OrderPublisher publisher;

    @Test
    void propagatesAsynchronousSendFailure() {
        OrderEvent event = new OrderEvent("order-42");
        var sendFuture =
                new CompletableFuture<SendResult<String, OrderEvent>>();

        when(kafkaTemplate.send("orders", "order-42", event))
                .thenReturn(sendFuture);

        CompletableFuture<SendResult<String, OrderEvent>> result =
                publisher.publish(event);

        assertThat(result).isNotNull();
        assertThat(result.isDone()).isFalse();

        sendFuture.completeExceptionally(
                new org.apache.kafka.common.errors.TimeoutException(
                        "simulated broker timeout"));

        assertThatThrownBy(result::join)
                .isInstanceOf(CompletionException.class)
                .hasCauseInstanceOf(
                        org.apache.kafka.common.errors.TimeoutException.class);

        verify(kafkaTemplate).send("orders", "order-42", event);
    }
}
~~~

The test explicitly completes the future with an exception, without needing to start a broker or wait for a real timeout. If the publisher attaches a callback to record metrics, add assertions that the failure counter increments and the success counter does not.

Note: `join()` wraps asynchronous errors in `CompletionException`; `get()` wraps them in `ExecutionException`. When asserting exception types, inspect the cause or unwrap the wrapper. Do not assert that all errors use the same wrapper if an error path can throw synchronously.

### 4.2. Testing synchronous exceptions when calling send

A mocked `KafkaTemplate` can throw an exception directly from the invocation:

~~~java
@Test
void exposesSynchronousSendInvocationFailure() {
    OrderEvent event = new OrderEvent("order-42");

    when(kafkaTemplate.send("orders", "order-42", event))
            .thenThrow(new KafkaException("producer is unavailable"));

    assertThatThrownBy(() -> publisher.publish(event))
            .isInstanceOf(KafkaException.class)
            .hasMessageContaining("producer is unavailable");
}
~~~

This test fits when the publisher preserves `KafkaTemplate`'s contract and lets synchronous exceptions propagate. If the publisher converts synchronous errors into failed futures via `publishSafely()`, assert that the returned future fails:

~~~java
@Test
void convertsSynchronousFailureToFailedFutureWhenApiRequiresIt() {
    OrderEvent event = new OrderEvent("order-42");

    when(kafkaTemplate.send("orders", "order-42", event))
            .thenThrow(new KafkaException("producer is unavailable"));

    CompletableFuture<SendResult<String, OrderEvent>> result =
            publisher.publishSafely(event);

    assertThat(result.isCompletedExceptionally()).isTrue();
    assertThatThrownBy(result::join)
            .isInstanceOf(CompletionException.class)
            .hasCauseInstanceOf(KafkaException.class);
}
~~~

The two examples illustrate two different API contracts. Choose the contract that matches your application and keep it consistent for callers.

### 4.3. Verifying callbacks do not swallow errors

If the publisher updates metrics/logs inside `whenComplete`, verify:

- The returned future still fails when the original future fails.
- The failure metric is incremented exactly once per failed send.
- The success metric does not increment when a send fails.
- The callback does not log payloads, credentials, or sensitive data.
- An exception inside metric-recording code does not obscure the original send failure cause.

Do not only verify that `kafkaTemplate.send()` was invoked. The key assertion is that the caller observes the right outcome.

### 4.4. Verifying exception classification

If the application classifies errors into retryable and non-retryable, test each category with a parameterized test:

~~~java
@ParameterizedTest
@MethodSource("nonRetryableFailures")
void doesNotRetryPermanentSendFailures(RuntimeException failure) {
    // Arrange: publisher receives failure from KafkaTemplate.
    // Act: trigger error handling path.
    // Assert: no retry is scheduled and failure is returned to caller.
}

static Stream<Arguments> nonRetryableFailures() {
    return Stream.of(
            Arguments.of(new SerializationException("bad payload")),
            Arguments.of(new RecordTooLargeException("record too large")),
            Arguments.of(new AuthorizationException("not authorized"))
    );
}
~~~

This is an illustrative skeleton; specific constructors and exception classes must match the project's Kafka client version. Retry only transient failures allowed by policy. Do not endlessly retry schema, authorization, or unsendable payload errors.

## 5. Testing KafkaTemplate with MockProducer

`MockProducer` belongs to the Kafka client and lets you control the next send and callback outcome without a broker. Combine `MockProducer` with a real `KafkaTemplate` to verify how Spring Kafka translates producer results into `CompletableFuture<SendResult<...>>`.

### 5.1. Creating a ProducerFactory that returns MockProducer

The example below uses Mockito to supply the mock producer:

~~~java
@SuppressWarnings("unchecked")
private ProducerFactory<String, String> producerFactoryFor(
        MockProducer<String, String> mockProducer) {
    ProducerFactory<String, String> producerFactory =
            Mockito.mock(ProducerFactory.class);
    when(producerFactory.createProducer()).thenReturn(mockProducer);
    return producerFactory;
}
~~~

If your Spring Kafka version uses different overloads or factory APIs, adapt the mock to that version's interface. For non-transactional tests, the factory must return a non-transactional producer. Each test should use its own producer instance so completion/history state does not leak across tests.

### 5.2. Simulating a broker error

~~~java
@Test
void completesKafkaTemplateFutureExceptionallyWhenProducerSendFails()
        throws Exception {
    MockProducer<String, String> mockProducer =
            new MockProducer<>(
                    true,
                    new StringSerializer(),
                    new StringSerializer());

    mockProducer.errorNext(
            new org.apache.kafka.common.errors.TimeoutException(
                    "simulated send timeout"));

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactoryFor(mockProducer));

    CompletableFuture<SendResult<String, String>> future =
            template.send("orders", "order-42", "payload");

    assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
            .isInstanceOf(ExecutionException.class)
            .hasCauseInstanceOf(
                    org.apache.kafka.common.errors.TimeoutException.class);
}
~~~

`errorNext()` configures an error for the next send on `MockProducer`. With `autoComplete=true`, the result completes automatically and KafkaTemplate's callback runs within the test. Therefore, no sleep is needed to wait for the callback.

This test verifies the path from the producer callback to KafkaTemplate's future. It does not simulate internal Kafka broker/network retries and does not replace integration tests against a real broker.

### 5.3. Testing the success path as a control

Include a control test to confirm the fixture works:

~~~java
@Test
void completesFutureWithMetadataWhenMockProducerSucceeds()
        throws Exception {
    MockProducer<String, String> mockProducer =
            new MockProducer<>(
                    true,
                    new StringSerializer(),
                    new StringSerializer());

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactoryFor(mockProducer));

    SendResult<String, String> result =
            template.send("orders", "order-42", "payload")
                    .get(2, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic()).isEqualTo("orders");
    assertThat(result.getProducerRecord().key()).isEqualTo("order-42");
    assertThat(mockProducer.history()).hasSize(1);
}
~~~

Specific metadata from `MockProducer` is synthetic. Do not use this test to verify partitioners, broker acknowledgements, or replication.

### 5.4. Testing ProducerListener

`KafkaTemplate` supports `ProducerListener` to receive send success/error notifications. This listener can be used to update metrics or write logs:

~~~java
AtomicReference<Exception> observedFailure = new AtomicReference<>();

template.setProducerListener(new ProducerListener<String, String>() {
    @Override
    public void onError(
            ProducerRecord<String, String> record,
            RecordMetadata metadata,
            Exception exception) {
        observedFailure.set(exception);
    }
});
~~~

After invoking send with `MockProducer.errorNext(...)`, wait for the future to complete and then inspect `observedFailure.get()`. For send failures before metadata is available, the metadata parameter can be `null`; listener code must handle that case.

`ProducerListener` is an additional observation hook. It does not replace returning the future to the caller or handling synchronous exceptions.

## 6. Testing producer initialization and synchronous errors

Pre-send failures usually cannot be simulated with `MockProducer.errorNext()` alone, because that method simulates a send callback failure. Separate tests by where the error arises.

### 6.1. ProducerFactory fails to create a producer

You can mock `ProducerFactory.createProducer()` to throw an exception:

~~~java
@Test
void handlesProducerCreationFailure() {
    ProducerFactory<String, String> factory =
            Mockito.mock(ProducerFactory.class);
    when(factory.createProducer())
            .thenThrow(new KafkaException("cannot create producer"));

    KafkaTemplate<String, String> template = new KafkaTemplate<>(factory);

    assertThatThrownBy(() -> template.send("orders", "payload"))
            .isInstanceOf(KafkaException.class)
            .hasMessageContaining("cannot create producer");
}
~~~

If your version wraps the error in another exception type, adjust the assertion to match the actual contract. What must be verified is that the error is not ignored and the caller can detect that the producer was not created.

### 6.2. Serializer throws an exception

A serializer can fail due to a malformed payload or invalid schema. You can test the serializer directly:

~~~java
class FailingStringSerializer implements Serializer<String> {

    @Override
    public byte[] serialize(String topic, String data) {
        throw new SerializationException("cannot serialize value");
    }
}
~~~

Then use the serializer in a producer test or test the mapping/serialization component separately. When writing tests with `MockProducer`, verify that the Kafka client version actually invokes the serializer on the send path in use. If you need to prove that `KafkaProducer` itself handles serializer failures as in production, use a real producer client with a test broker, or a dedicated test that does not depend on a broker if serialization runs before network I/O.

Do not just verify that the exception is thrown. Confirm that the record is not counted as a successful send, does not increment success metrics, and does not trigger unbounded retries for an unserializable payload.

### 6.3. Metadata or buffer wait errors

The Kafka producer may wait for metadata or buffer space before `send()` returns. `max.block.ms` bounds some of these synchronous waits. Testing this class of error requires a real producer client with controlled configuration, or mocking the corresponding producer/metadata acquisition point.

Do not use a unit test containing `Thread.sleep()` to simulate a full buffer. When real behavior needs to be tested, configure a test environment with low time limits, apply deliberate pressure, and use test timeouts to avoid hanging the build.

## 7. Testing retries and delivery timeout

### 7.1. Distinguishing Kafka client retries from application retries

The Kafka producer client has internal retries for certain recoverable errors. Relevant settings include:

- `retries`: number of times the client retries per policy and client version.
- `delivery.timeout.ms`: total maximum time allowed to report record delivery, including waiting and retries.
- `request.timeout.ms`: limit for waiting on a request response.
- `linger.ms`: time the producer may wait to batch records before sending.
- `max.block.ms`: limit for certain synchronous waits for metadata or buffer space.
- `enable.idempotence`: helps prevent duplicates caused by internal producer retries within the session/producer protocol scope.

Application retries are a separate layer: the service receives a failed future and explicitly calls `send()` again. If both internal retries and application retries are enabled, the total number of send attempts and overall wait time can exceed expectations.

Do not add up retry counts with a naive formula if client versions have different semantics. Measure total elapsed time, application-level send call counts, and producer metrics in a test environment.

### 7.2. Testing bounded retries

If the application has a retry policy, test these cases:

1. Transient error on the first attempt, success on the next: the application resends the expected number of times.
2. All attempts fail: stops after the limit and returns the final error.
3. Non-retryable error: no retry is scheduled.
4. Backoff has a maximum bound and does not create an infinite loop.
5. Business deadline expires: stops retrying when the result is no longer useful.
6. Each retry preserves the key/correlation ID needed for tracing and deduplication.

Example logic to test using mocked futures completed sequentially:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> first =
        new CompletableFuture<>();
CompletableFuture<SendResult<String, OrderEvent>> second =
        new CompletableFuture<>();

when(kafkaTemplate.send(eq("orders"), anyString(), any(OrderEvent.class)))
        .thenReturn(first, second);

// Call publisher, fail first with a retryable error,
// trigger the scheduler/test clock, then complete second successfully.
// Assert send invocation count and final result.
~~~

To test backoff without waiting real wall-clock time, inject a controllable scheduler, clock, or retry abstraction. If the code uses a retry framework, use that framework's test support to verify attempt counts and delays.

### 7.3. Choosing retryable exceptions

Do not retry every `Exception`. Classify by root cause and policy:

| Error type | Typical appropriate behavior |
|---|---|
| Transient network error, broker leader change | Let the Kafka client retry per configuration; evaluate application retry if needed |
| Timeout after client exhausts delivery deadline | Can retry at application layer if business logic permits and idempotency exists |
| Authorization/ACL | Do not retry repeatedly; fix permissions/configuration |
| Serialization/schema error | Do not retry the same payload; fix data or schema |
| Record too large | Do not retry unchanged; adjust size or limits |
| Missing topic/partition due to misconfiguration | Do not retry blindly; verify configuration and provisioning |
| Producer closed or application shutting down | Handle per lifecycle; do not create infinite background retries |

A timeout does not prove the broker failed to write the record. The broker may have received and written the data while the acknowledgement failed to reach the producer. If the application resends, duplicates can occur at the business layer. Therefore, retries require idempotency or deduplication when duplicates have side effects.

### 7.4. Idempotence does not replace business idempotency

`enable.idempotence=true` helps the producer protocol handle duplicates from internal retries within a single producer session according to Kafka semantics. It does not guarantee that an application-level resend after a timeout, restart, or new process will produce only one business event.

To control duplicates at the business level:

- Use a stable event ID across all retry attempts.
- Design consumers/downstream handlers to be idempotent or deduplicate by event ID.
- Persist send state and business state in the same appropriate transaction, or use the outbox pattern when atomicity between database and Kafka is required.
- Verify duplicate handling with integration tests, not just mock invocation counts.

## 8. Testing timeouts and unavailable brokers

### 8.1. Test-specific timeout configuration

When running integration tests, shorter deadlines than production can be used so tests finish quickly, while still obeying Kafka client configuration constraints. Illustrative example:

~~~properties
request.timeout.ms=1000
delivery.timeout.ms=4000
linger.ms=0
max.block.ms=1500
~~~

`delivery.timeout.ms` must align with the sum of request timeout and linger as required by the Kafka client version in use. If the configuration is invalid, the producer may refuse to start; that is a test configuration error, not proof that send failure was tested.

Do not set timeouts so low that tests fail flakily on CI. The goal is to bound test duration in a controlled environment, not to create a timing race.

### 8.2. Embedded Kafka for integration tests

`spring-kafka-test` provides `@EmbeddedKafka` to run a broker inside tests. Use it to validate real application configuration, serialization, topic routing, and round-trip behavior:

~~~java
@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "orders",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@DirtiesContext
class OrderPublisherIntegrationTest {

    @Autowired
    KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @Test
    void sendsEventToEmbeddedBroker() throws Exception {
        OrderEvent event = new OrderEvent("order-42");

        SendResult<String, OrderEvent> result =
                kafkaTemplate.send("orders", event.orderId(), event)
                        .get(5, TimeUnit.SECONDS);

        assertThat(result.getRecordMetadata().topic()).isEqualTo("orders");
    }
}
~~~

This is a happy-path test. An embedded broker is useful for integration, but does not automatically produce every broker/network failure scenario. Stopping a broker or breaking connections can depend on lifecycle, timing, and how the test framework manages the broker; avoid writing tests around an uncontrolled shutdown if state cannot be controlled.

### 8.3. Controlled fault injection

To test an unavailable broker, network partition, or lost acknowledgements:

1. Start an isolated Kafka broker for the test, typically via Testcontainers or an isolated integration environment.
2. Place a TCP proxy that can toggle connectivity between the producer and broker, or use the test environment's fault injection mechanism.
3. Create the producer once the environment is in a deterministic state.
4. Trigger the fault at the right point: before send, after the request is sent, or while waiting for acknowledgement.
5. Invoke send and await the future with a finite timeout.
6. Verify the final error type, completion duration, metrics, and retry behavior.
7. Restore the network/broker and confirm the producer can send again per supported lifecycle.

To test timeouts, configure `delivery.timeout.ms` appropriately for the test and ensure the proxy holds the fault long enough. Do not assume every broker outage produces one exact exception type; the Kafka client may retry, refresh metadata, and only return the final error after the deadline.

### 8.4. Testing authorization and oversized records

Authorization failures can be tested in a Kafka environment with ACLs enabled:

- Grant the principal connection permission but omit topic write permission.
- Send a record and verify the future fails with the appropriate authorization error.
- Verify the application does not repeatedly retry configuration/permission errors.
- Restore the ACL and verify sending succeeds.

Oversized records must be tested against matching broker/topic/producer configuration limits. Raising a limit on only one side does not guarantee successful sends; broker, topic, and consumer must have compatible settings. Use test payloads without real data and document the applied limits.

## 9. Testing transactional producers

When using Kafka transactions, distinguish three events:

1. The producer sends the record and receives an acknowledgement.
2. The application calls commit transaction.
3. The broker confirms transaction commit.

A send future succeeding in the first step does not prove the transaction committed. If the transaction aborts, a consumer using `isolation.level=read_committed` must not see records belonging to the aborted transaction.

Transaction tests should cover:

- Successful send and commit; `read_committed` consumer receives the record.
- Sending a record and explicitly throwing an exception inside the transaction; the transaction aborts and the `read_committed` consumer does not receive the record.
- Commit fails due to broker/network; the application reports a transaction error and does not mark the business operation complete.
- The producer transactional ID is configured properly and does not collide in a way that causes unexpected fencing.

Conceptual example with KafkaTemplate:

~~~java
template.executeInTransaction(operations -> {
    operations.send("orders", "order-42", "payload");
    throw new IllegalStateException("force rollback in test");
});
~~~

Tests must verify transaction rollback per the actual API/version and use a `read_committed` consumer to inspect the outcome. Configure the producer transaction ID prefix, transaction manager, and consumer isolation appropriately for the Spring Kafka version. Do not use a test that only inspects the send future to conclude that the transaction committed.

## 10. Checking callbacks, threads, and test timeouts

### 10.1. Do not discard the future

The following code creates a risk of silently ignoring failures:

~~~java
kafkaTemplate.send("orders", key, event);
return "accepted";
~~~

If business logic needs to know whether Kafka acknowledged the record, returning `accepted` immediately after calling send only means the application started sending. Return the future, handle the callback, or persist an explicit pending state.

### 10.2. Do not wait indefinitely

In tests, always set a wait deadline:

~~~java
SendResult<String, String> result =
        future.get(3, TimeUnit.SECONDS);
~~~

If the future does not complete, the test must fail with a timeout to expose a hung callback/future. The timeout on `future.get(...)` only limits how long the test waits; it does not alter the producer's `delivery.timeout.ms`.

### 10.3. Avoid sleeps and race conditions

Do not use:

~~~java
Thread.sleep(2000);
assertThat(failureCounter.count()).isEqualTo(1);
~~~

Instead:

- Complete the future explicitly in unit tests.
- Use `CountDownLatch` or a future with a timeout when callbacks execute on another thread.
- Use Awaitility if the project already has the dependency and the condition being awaited is real asynchronous state.
- Use a fake test clock/scheduler for backoff.
- Use real timeouts only in integration/fault-injection tests with appropriate deadlines.

Callbacks may execute on the Kafka producer thread or the thread completing the future depending on implementation. Do not assume callbacks always run on a separate thread. Avoid long-blocking callbacks, network waits, or heavy operations that stall the send thread.

## 11. Recommended test matrix

| Case | How to simulate | Outcome to verify |
|---|---|---|
| Successful send | `MockProducer` auto-complete or embedded broker | Future succeeds, metadata is valid |
| Broker callback error | `MockProducer.errorNext(...)` | Future fails, cause is preserved |
| Producer creation failure | Mock `ProducerFactory.createProducer()` throwing error | Synchronous error propagated or normalized per API |
| Serializer error | Serializer throws `SerializationException` | Not reported as success, no infinite retry of bad payload |
| Record delivery timeout | Fault injection/unresponsive broker | Future fails within configured deadline |
| Authorization failure | Kafka ACL test | Error classified as non-retryable |
| Record too large | Configure broker/topic limits | Clear error, no infinite loop |
| Retryable network failure | Proxy causing controlled disconnect | Bounded retries, correct final outcome |
| Retry fails first, succeeds next | Mock future/scheduler | Send count and final result match policy |
| Retries exhausted | All send attempts fail | Final error returned, no remaining retry tasks |
| Transaction abort | Throw exception inside transaction | `read_committed` consumer sees no record |
| Transaction commit error | Fault injection during commit | Business operation not reported complete |
| Shutdown while sending | Controlled context/producer close | Does not hang indefinitely, failure is observed |

You do not need every case in a single test class. Keep unit tests fast and deterministic; place tests requiring a broker, ACLs, or proxy into a separate integration suite.

## 12. Common mistakes when writing tests

### Only verifying the send invocation

`verify(kafkaTemplate).send(...)` only proves the code called the method. It does not prove the future was observed, exceptions reached the caller, or metrics reflect the true outcome.

### Injecting exceptions at the wrong layer

`MockProducer.errorNext()` simulates a send callback failure. It does not simulate `ProducerFactory` failing to create a producer. Use the fixture matching the failure location.

### Using `get()` without handling synchronous errors

If `send()` throws an exception before returning a future, the future variable is never assigned and `get()` cannot catch that failure. Test the synchronous invocation path separately.

### Asserting the wrong exception wrapper

`join()` and `get()` use different wrappers for asynchronous failures. Check the cause instead of comparing only the wrapper's message. For synchronous errors, assertions may need to inspect the root exception.

### Waiting for production timeouts in tests

Keeping a long delivery timeout in a fault-injection test can drag out the build. Use test-specific configuration and set wait deadlines in the test framework. Ensure the test configuration remains valid for the Kafka client.

### Assuming timeout means the record was not written

The producer can lose the acknowledgement after the broker has already written the record. Retrying at the application layer can produce duplicates. Verify event IDs, idempotency, and data reconciliation.

### Using Embedded Kafka to prove every network failure

An embedded broker is suitable for basic integration. Testing disconnects, timeouts, or broker failures requires controlled fault injection and assertions matching real client behavior.

### Letting callbacks swallow exceptions

A callback may log an error while the original future remains failed; conversely, code using `exceptionally` to return a default value can make callers believe the send succeeded. Define the error contract clearly and test the final state of the future.

## 13. Producer send failure test completion checklist

### Design

- [ ] Identify the Spring Kafka version and future type in use.
- [ ] Classify synchronous, asynchronous, and transaction errors.
- [ ] Determine whether callers should receive an exception or a failed future.
- [ ] Define which errors are retryable and the retry limit.
- [ ] Define how duplicates are prevented at the business layer.

### Unit tests

- [ ] Test future completing exceptionally.
- [ ] Test exception thrown directly from the send call.
- [ ] Test that callers do not receive a successful result when send fails.
- [ ] Test success and failure metrics/logs are accurate.
- [ ] Test retryable/non-retryable classification.
- [ ] Test retry count, backoff, and stopping when the limit is reached.

### KafkaTemplate/Integration tests

- [ ] Test `MockProducer.errorNext()` propagating errors to the future.
- [ ] Test the success path and metadata.
- [ ] Test ProducerFactory failing to create a producer.
- [ ] Test serializers if serialization is a risk for the application.
- [ ] Test broker/ACLs/timeouts in a controlled environment when needed.
- [ ] Test transaction commit/abort if the producer uses transactions.

### Stability

- [ ] Every future in tests has a finite wait timeout.
- [ ] No arbitrary sleeps are used to wait for callbacks.
- [ ] MockProducer/factories do not share state across tests.
- [ ] Tests clean up producers, contexts, proxies, and containers.
- [ ] Test failures are reproducible on CI with clear configuration.

## 14. Test result reporting

When recording results in a pull request or reliability report, state the test layer, failure injection, and observed evidence:

~~~text
Test name:
Spring Kafka version:
Kafka client version:
Test layer: unit / MockProducer / embedded broker / fault injection
Failure point:
Injected exception or fault:
Producer timeout configuration:
Expected result:
Observed future/callback result:
Retry attempts:
Duplicate/idempotency assertion:
Transaction outcome (if applicable):
Cleanup status:
~~~

A test is meaningful only when readers know where the fault was injected and which behavior the assertions prove. State fixture limitations explicitly: MockProducer tests client API callbacks/futures; an embedded broker tests broker integration; fault injection tests network/broker failure behavior.

## 15. Spring Kafka version compatibility

Starting in Spring Kafka 3.0, `KafkaTemplate.send(...)` APIs return `CompletableFuture`. Applications on Spring Kafka 2.x commonly use `ListenableFuture` and Spring callbacks:

~~~java
ListenableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send("orders", event.orderId(), event);

future.addCallback(
        result -> log.info("Send completed"),
        exception -> log.warn("Send failed", exception));
~~~

This is the legacy API form to recognize when reading codebases. Do not mix `ListenableFuture` with `CompletableFuture` examples in the same test if the project has not upgraded yet. When upgrading versions:

- Update return types and callbacks.
- Update assertions for exceptions/wrappers.
- Verify `MockProducer`, `ProducerFactory`, and corresponding Kafka client APIs.
- Re-run transaction, retry, and shutdown tests because semantics depend on version and configuration.

## 16. Post-test operational principles

When tests uncover producer send failures, the results should lead to clear operational behavior: logs with enough information for tracing, metrics showing failure rates, alerts with appropriate thresholds, retries that stop on time, and records never falsely marked successful. For critical flows, provide event ID reconciliation or an outbox to identify which records were sent and which need reprocessing.

Do not use retries to mask persistent configuration errors. Do not reset or delete send state merely to make dashboards look clean. When a timeout may have occurred after the broker wrote the record, investigate duplicates via key/event ID and consumer state before replaying.
