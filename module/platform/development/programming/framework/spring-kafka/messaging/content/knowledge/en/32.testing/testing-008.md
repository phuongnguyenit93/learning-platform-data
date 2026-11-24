# Waiting for Records with Awaitility or Polling

Kafka processes messages asynchronously. When a test calls `KafkaTemplate.send()`, the producer sends the record to the broker; afterwards, the consumer may need additional time to poll, deserialize, run the listener, update the database, and commit offsets. Therefore, a successful send does not mean the entire processing flow has completed at the moment the test continues.

In integration tests, avoid using a fixed `Thread.sleep()` to guess when a record will arrive. A short sleep can cause tests to fail on slow CI runners; a long sleep slows down the suite without proving the desired condition. Instead, **wait for a meaningful condition with a finite timeout**. Awaitility fits when waiting for final state or side effects; direct polling fits when a test needs to read Kafka records using a test-managed KafkaConsumer.

This lesson belongs to the **Testing** chapter of the **SPRING_KAFKA_MESSAGING** module and focuses on waiting for records and asynchronous processing results using Awaitility or polling while avoiding race conditions, infinite timeouts, and unstable tests.

## Learning Outcomes

After this lesson, you will be able to:

- Explain why Kafka integration tests need to wait for asynchronous results.
- Distinguish producer send acknowledgment from consumer listener completion.
- Use Awaitility to wait for listeners, database state, offsets, or DLT records.
- Use thread-safe collections/holders to pass results from the listener thread to the test thread.
- Use BlockingQueue or CountDownLatch with finite timeouts.
- Poll KafkaConsumer against a deadline instead of fixed sleeps.
- Wait for consumer assignment before publishing records when test ordering must be controlled.
- Distinguish polling data from polling a condition.
- Choose reasonable timeouts and poll intervals.
- Test retries, DLT, committed offsets, and side effects without creating flaky tests.
- Isolate topics, group IDs, and state between tests.

## 1. Why Must Kafka Tests Wait?

A producer-consumer flow usually involves multiple independent steps:

~~~mermaid
sequenceDiagram
    participant T as Test
    participant P as KafkaTemplate
    participant K as Kafka broker
    participant C as Consumer
    participant S as Listener service
    T->>P: send(record)
    P->>K: Produce request
    K-->>P: Broker acknowledgement
    P-->>T: Send future completes
    K-->>C: Record available
    C->>S: Invoke listener
    S-->>C: Processing completes
    Note over T,S: Test may need to wait for this result
~~~

The producer's future completes when the broker acknowledges the send according to producer configuration. It does not wait for the consumer to receive the record, the listener to finish, or the database to update.

Therefore, tests need to clarify what they are waiting for:

- Broker received the record.
- Listener was invoked.
- Listener finished processing.
- Database reached the expected state.
- Consumer group committed the offset.
- Failed record appeared in the DLT.

Each condition is a distinct milestone. Wait for the exact milestone the test is verifying.

## 2. Do Not Use Thread.sleep to Synchronize Tests

A test prone to issues:

~~~java
@Test
void shouldConsumeOrder() throws Exception {
    kafkaTemplate.send("orders.created", event);

    Thread.sleep(2_000);

    assertThat(orderRepository.findById(event.orderId()))
            .isPresent();
}
~~~

This test assumes two seconds is always enough for the consumer to process the record. It may pass locally, but on CI or during a broker rebalance it might take longer. Increasing the sleep to ten seconds only makes the test slower without guaranteeing the condition has occurred.

Replace it with waiting on state:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(orderRepository.findById(event.orderId()))
                        .isPresent()
        );
~~~

Awaitility re-evaluates the assertion until it succeeds or times out. The test finishes immediately once the condition is met, instead of always waiting out a fixed sleep duration.

Do not use `Thread.sleep` as a synchronization mechanism between producer, consumer, and test. If business processing time or timeouts need to be simulated, control them using a clock, latch, or appropriate test double.

## 3. Adding Awaitility to Tests

Awaitility is a library for waiting until an eventual condition is met with configurable timeouts and poll intervals.

If the project does not yet include Awaitility, add the dependency in `test` scope. Maven example:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <scope>test</scope>
</dependency>
~~~

With Gradle:

~~~groovy
testImplementation("org.awaitility:awaitility")
~~~

If using Spring Boot dependency management, let the project's dependency management handle the version; otherwise, declare a version standardized in the build.

Common imports:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
~~~

Awaitility does not create a Kafka broker and does not replace EmbeddedKafka or Testcontainers. It only coordinates condition waiting in tests.

## 4. Configuring Timeout and Poll Interval

A basic Awaitility call:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .until(() -> orderRepository.existsById(orderId));
~~~

Meaning:

- `atMost`: upper bound on total wait time.
- `pollInterval`: interval between checks.
- `until`: condition that must return true.

If informative assertion failures are needed, use `untilAsserted`:

~~~java
await()
        .alias("order should be persisted by Kafka listener")
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(orderRepository.findById(orderId))
                        .isPresent()
        );
~~~

Choose a timeout long enough for consumer startup, group join, polling, processing, and state updates. The poll interval does not need to be tiny; checking every few milliseconds usually just adds unnecessary load to the database or broker.

Do not use infinite timeouts. When a timeout expires, the test should fail to show which condition did not occur.

## 5. Waiting for a Listener to Receive Records Using Thread-Safe Data

Listeners run on consumer threads, while tests run on the test thread. Do not share a plain `ArrayList` between two threads without synchronization.

You can use a `BlockingQueue`:

~~~java
@Component
public class TestOrderListener {

    private final BlockingQueue<OrderCreatedEvent> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "${test.kafka.topic}",
            groupId = "test-orders-listener"
    )
    public void listen(OrderCreatedEvent event) {
        received.add(event);
    }

    public BlockingQueue<OrderCreatedEvent> received() {
        return received;
    }
}
~~~

The test sends a record and waits with `poll(timeout)`:

~~~java
@Test
void shouldReceiveOrderEvent() throws Exception {
    OrderCreatedEvent event = sampleEvent();

    kafkaTemplate.send(topic, event.orderId(), event)
            .get(10, TimeUnit.SECONDS);

    OrderCreatedEvent actual =
            testOrderListener.received().poll(10, TimeUnit.SECONDS);

    assertThat(actual).isEqualTo(event);
}
~~~

`BlockingQueue.poll` waits up to the specified time and returns null if no record arrives. This is concise when the test only needs to retrieve a single result.

Clear the queue before each test if the listener bean is reused in the same application context:

~~~java
@BeforeEach
void clearReceivedEvents() {
    testOrderListener.received().clear();
}
~~~

If tests run in parallel, each test should have its own listener state or use correlation/event IDs to distinguish results.

## 6. Using Awaitility with AtomicReference or Thread-Safe Collections

If you want to wait using Awaitility, you can store the result in an `AtomicReference`:

~~~java
@Component
public class AwaitableOrderListener {

    private final AtomicReference<OrderCreatedEvent> received =
            new AtomicReference<>();

    @KafkaListener(
            topics = "${test.kafka.topic}",
            groupId = "test-awaitable-orders"
    )
    public void listen(OrderCreatedEvent event) {
        received.set(event);
    }

    public OrderCreatedEvent received() {
        return received.get();
    }

    public void reset() {
        received.set(null);
    }
}
~~~

Test:

~~~java
@Test
void shouldEventuallyReceiveExpectedEvent() throws Exception {
    OrderCreatedEvent expected = sampleEvent();

    awaitableOrderListener.reset();

    kafkaTemplate.send(topic, expected.orderId(), expected)
            .get(10, TimeUnit.SECONDS);

    await()
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() ->
                    assertThat(awaitableOrderListener.received())
                            .isEqualTo(expected)
            );
}
~~~

For multiple records, use `CopyOnWriteArrayList` or another thread-safe collection:

~~~java
private final List<OrderCreatedEvent> received =
        new CopyOnWriteArrayList<>();
~~~

And wait for enough records:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(received).hasSize(3)
        );
~~~

Awaitility conditions may be evaluated multiple times. Do not put destructive data-consuming operations like `queue.take()`, `consumer.poll()`, or clearing a collection inside the condition; the first evaluation could consume the data, leaving nothing for subsequent checks.

## 7. When to Use CountDownLatch or BlockingQueue Instead of Awaitility?

Awaitility fits when a test waits on state that can be queried repeatedly. If the listener only needs to signal "a record was received", `CountDownLatch` or `BlockingQueue` is often simpler.

Latch example:

~~~java
@Component
public class LatchOrderListener {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<OrderCreatedEvent> received =
            new AtomicReference<>();

    @KafkaListener(
            topics = "${test.kafka.topic}",
            groupId = "test-latch-orders"
    )
    public void listen(OrderCreatedEvent event) {
        received.set(event);
        latch.countDown();
    }

    public boolean await(Duration timeout) throws InterruptedException {
        return latch.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public OrderCreatedEvent received() {
        return received.get();
    }
}
~~~

Test:

~~~java
kafkaTemplate.send(topic, event).get(10, TimeUnit.SECONDS);

assertThat(listener.await(Duration.ofSeconds(10))).isTrue();
assertThat(listener.received()).isEqualTo(event);
~~~

A latch only counts down and does not reset automatically. If reusing a listener across multiple tests, create a new latch per test or use separate listener/test contexts. Do not await a latch indefinitely.

## 8. Distinguishing Producer Acknowledgment Wait from Consumer Completion Wait

In Spring Kafka 3.x, `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K, V>>`. You can await broker acknowledgment with `get(timeout)`:

~~~java
SendResult<String, OrderCreatedEvent> result =
        kafkaTemplate.send(topic, event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

assertThat(result.getRecordMetadata().topic()).isEqualTo(topic);
~~~

This verifies that the producer sent successfully according to its acknowledgment settings. It does not verify that the listener processed the record.

Afterwards, use Awaitility, a queue, or consumer polling to wait for consumer-side results.

In older Spring Kafka versions, the send API may return `ListenableFuture`. Use the API matching your dependency version; do not mix examples from both API generations in the same codebase.

Do not ignore the future if the test needs to verify producer send. If sending fails, the test should fail at the publish step rather than waiting for the consumer until timeout and reporting a confusing error.

## 9. Direct Polling with KafkaConsumer

Sometimes a test needs to read records directly instead of waiting on a `@KafkaListener`. You can create a test KafkaConsumer, subscribe to a topic, and call `poll(Duration)`.

Example consumer setup:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, "test-reader-" + UUID.randomUUID());
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class);
~~~

If using JsonDeserializer, configure target types/trusted packages or mapping matching the test contract. You can use StringDeserializer or ByteArrayDeserializer when the test only needs to inspect wire payloads.

Subscribe:

~~~java
consumer.subscribe(List.of(topic));
~~~

After subscribing, the consumer may not have an assignment immediately. Call poll to join the group and wait for assignment before sending records if the test needs to avoid races with `auto.offset.reset=latest`.

## 10. Waiting for Consumer Assignment Before Sending Records

A common mistake is creating a consumer, subscribing, and immediately sending records. The consumer may not have completed the group join yet; if using `latest`, it may start at the end of the log after the record was already written.

You can wait for assignment with a deadline:

~~~java
consumer.subscribe(List.of(topic));

long assignmentDeadline =
        System.nanoTime() + Duration.ofSeconds(10).toNanos();

while (consumer.assignment().isEmpty()
        && System.nanoTime() < assignmentDeadline) {
    consumer.poll(Duration.ofMillis(100));
}

assertThat(consumer.assignment()).isNotEmpty();
~~~

This poll loop must run on the exact thread that owns the KafkaConsumer. KafkaConsumer is not thread-safe; never call `poll()` from one thread while another thread uses the same consumer.

Once assignment is ready, the test can send records and start the poll loop to read them. If the topic has multiple partitions or complex subscriptions, verify that the assignment contains the expected partitions rather than only checking that the collection is non-empty.

## 11. Polling with a Deadline Instead of Infinite Polling

A polling helper with an explicit timeout:

~~~java
static <K, V> List<ConsumerRecord<K, V>> pollUntilCount(
        Consumer<K, V> consumer,
        int expectedCount,
        Duration timeout) {

    long deadline = System.nanoTime() + timeout.toNanos();
    List<ConsumerRecord<K, V>> collected = new ArrayList<>();

    while (collected.size() < expectedCount
            && System.nanoTime() < deadline) {

        ConsumerRecords<K, V> batch =
                consumer.poll(Duration.ofMillis(100));

        batch.forEach(collected::add);
    }

    if (collected.size() < expectedCount) {
        throw new AssertionError(
                "Expected " + expectedCount
                + " records but received " + collected.size()
        );
    }

    return collected;
}
~~~

The helper stops once enough records are received or the deadline expires. It does not use `while(true)` and never waits indefinitely.

In tests, ensure the consumer has subscribed and received an assignment before sending records if offset reset must be controlled. After reading, assert topic, key, value, partition, offset, and headers.

If you need to read exactly one record, pass `expectedCount` as one. If you need to verify there are no extra or duplicate records, explicitly define the observation window and test conditions; receiving the first N records alone does not prove there will be no (N+1)th record.

## 12. Polling a Condition vs. Polling Kafka Records

Both techniques are called polling, but they have different responsibilities:

| Technique | Target Being Checked | Typically Used When |
|---|---|---|
| Awaitility polling | A repeatable queryable condition | A database row appears, listener state changes, offset is committed. |
| KafkaConsumer.poll | Records from the broker | Test needs to inspect wire records, headers, partition, and offset. |
| BlockingQueue.poll | Results pushed into a queue by the listener | Test needs to retrieve records received by the listener. |
| CountDownLatch.await | Completion signal | Test needs to know a callback ran. |

Do not place `KafkaConsumer.poll` inside an Awaitility condition if the same consumer could be called from multiple threads. When using Awaitility to wait for data from a listener, wait on a thread-safe holder such as `AtomicReference` or a queue peek.

If a test needs to read records directly, use a synchronous poll loop on the test thread with a deadline.

## 13. Using EmbeddedKafka to Test Listeners

Spring Kafka provides `@EmbeddedKafka` to run an embedded broker in integration tests. Example:

~~~java
@SpringBootTest
@EmbeddedKafka(
        topics = "orders.created",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderListenerIntegrationTest {
    // Inject KafkaTemplate and listener capture.
}
~~~

Tests can send records with `KafkaTemplate` and then wait for the listener to update a queue or database.

EmbeddedKafka fits fast tests and verifying Spring Kafka integration. However, an embedded broker does not fully replace a production Kafka environment, especially when verifying SASL/TLS, multiple brokers, replication, rack awareness, or cluster-version-dependent behavior.

Use Testcontainers or a dedicated integration environment for scenarios requiring a more production-like broker.

## 14. Using Testcontainers When a More Realistic Broker Is Needed

Testcontainers can start a Kafka container in tests and provide bootstrap servers to the Spring context.

General steps:

1. Start the Kafka container before the Spring context creates Kafka clients.
2. Pass bootstrap servers into `spring.kafka.bootstrap-servers`.
3. Create topics or enable topic provisioning in tests.
4. Send records using `KafkaTemplate`.
5. Wait for the listener/side effects or read records using a test consumer.
6. Stop the container after tests finish.

Testcontainers is useful when testing specific broker versions, listener configs, transactions, or security. Pick an image and mode compatible with the active Kafka client/broker versions.

Do not start a new broker container for every assertion. Leverage test suite or class lifecycles when tests can share a broker while still isolating topics and group IDs.

## 15. Waiting for Database Side Effects After Listener Execution

A listener may receive a record and then update the database asynchronously. If the test goal is to verify business outcomes, wait for the database state rather than only waiting for listener invocation.

~~~java
kafkaTemplate.send(topic, event).get(10, TimeUnit.SECONDS);

await()
        .alias("order should be stored")
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            assertThat(orderRepository.findById(event.orderId()))
                    .hasValueSatisfying(order ->
                            assertThat(order.getStatus()).isEqualTo("CREATED")
                    );
        });
~~~

The condition must query observable state without causing side effects. If the repository reads through a cache, clarify whether the test is verifying the database or the cache.

If the listener runs in its own database transaction, do not wrap the entire test method in a transaction and expect the consumer thread to see uncommitted data. The test thread's transaction and the listener thread's transaction are two separate transactions.

## 16. Waiting for Committed Offsets

Some tests need to verify that the listener processed the record and the consumer group committed the offset. You can query `AdminClient` and wait until the offset reaches the expected value.

General condition example:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            OffsetAndMetadata committed =
                    adminClient.listConsumerGroupOffsets(groupId)
                            .partitionsToOffsetAndMetadata()
                            .get(5, TimeUnit.SECONDS)
                            .get(new TopicPartition(topic, partition));

            assertThat(committed).isNotNull();
            assertThat(committed.offset()).isGreaterThan(expectedInputOffset);
        });
~~~

The committed offset is the next offset to read. If a test processes a record at offset 10, the expected committed offset is normally 11 or greater, depending on prior records and `AckMode`.

Do not use committed offsets as the sole proof of database side effects. Offsets can commit according to container settings; business tests should also verify business state.

If using `MANUAL` acknowledgment or transactions, determine the exact corresponding commit condition before writing assertions.

## 17. Waiting for Retries and Dead-Letter Records

When testing retries, a listener may be invoked multiple times before recovery. When testing DLT, wait for the record to appear on the DLT after the error handler publishes it successfully.

You can use a DLT test listener that records into a queue:

~~~java
@Component
public class TestDltListener {

    private final BlockingQueue<ConsumerRecord<String, byte[]>> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "orders.created.DLT",
            groupId = "test-dlt-reader"
    )
    public void listen(ConsumerRecord<String, byte[]> record) {
        received.add(record);
    }

    public BlockingQueue<ConsumerRecord<String, byte[]>> received() {
        return received;
    }
}
~~~

`ConsumerRecord<String, byte[]>` is only suitable when the DLT test listener's container factory uses `StringDeserializer` for keys and `ByteArrayDeserializer` for values. Listener Java parameter types do not automatically configure deserializers; if the DLT uses another serializer, select the matching value type and factory.

The test sends a failing record, then waits for the DLT record:

~~~java
ConsumerRecord<String, byte[]> deadLetter =
        dltListener.received().poll(15, TimeUnit.SECONDS);

assertThat(deadLetter).isNotNull();
assertThat(deadLetter.headers().lastHeader(
        KafkaHeaders.DLT_ORIGINAL_TOPIC
)).isNotNull();
~~~

The timeout must account for the configured retry count and backoff. If tests use long backoffs, shorten durations in a test profile or raise the bounded timeout; do not change production semantics solely to speed up tests.

If needing to verify retry counts, use a thread-safe counter or appropriate spy/mock and wait for the final condition. Never use sleep to guess when the third retry has happened.

## 18. Avoiding Flaky Tests Caused by Stale Data and Reused Consumer Groups

A test can receive records from a previous run if topics/group IDs are reused and offset resets behave unexpectedly.

Isolation measures:

- Use a dedicated or freshly created topic for the test.
- Use a unique group ID per test run when needing to read from the beginning.
- Set `auto.offset.reset` intentionally.
- Create the consumer and wait for assignment before sending records if using `latest`.
- Clear queues/capture state before each test.
- Do not run two tests writing to the same topic/group if they can affect each other's results.
- Close `KafkaConsumer`, `AdminClient`, and other resources after tests.
- Do not depend on test execution order.

`auto.offset.reset=earliest` applies only when the group has no valid committed offset. If the group already has an offset, the consumer resumes from the committed offset; changing `auto.offset.reset` does not automatically rewind data.

If sharing a topic, filter by a unique event ID and verify the exact record belonging to the current test.

## 19. Choosing Timeouts Based on Realistic Timings

Timeouts should neither be so short that loaded CI runners cause random failures, nor so long that real errors take minutes to surface.

Consider:

- Broker and Spring context startup time.
- Consumer group join/rebalance time.
- Poll timeouts and concurrency.
- Retry/backoff if applicable.
- Database or downstream processing time.
- Local, CI, and container runtime environments.
- Timeouts of the producer send itself and `AdminClient` requests.

You can use a longer timeout for initial startup and shorter timeouts once the listener is ready. Do not blindly increase every timeout when a test is flaky; identify which step is slow.

Timeout failure messages should mention the expected condition, topic, group ID, and event ID for easier diagnosis. Avoid reporting only "condition was not fulfilled" without context.

## 20. Common Pitfalls When Waiting for Records

| Mistake | Consequence | Fix |
|---|---|---|
| Using fixed `Thread.sleep` | Flaky or slow tests | Awaitility, queue/latch, or poll deadline. |
| Assuming completed send future means listener finished | Premature assertions | Wait for listener or side effects separately. |
| Awaitility condition drains a queue | Next poll sees no data | Use peek/`AtomicReference` in the condition; consume data after met. |
| Using `KafkaConsumer` from multiple threads | Violates thread-safety | Poll on a single thread only. |
| Sending before consumer assignment is ready with `latest` | Consumer may miss the sent record | Wait for assignment before producing or isolate topic/group. |
| Polling without a deadline | Test hangs forever | Use finite deadlines and timeouts. |
| Reusing an old group ID | Resumes from old committed offset | Create a separate group ID or manage offsets explicitly. |
| Waiting only for listener invocation | Does not prove database commit | Wait for the business state to verify. |
| Timeout shorter than retry/backoff | Test fails despite working code | Account for total retry and recovery time. |
| Sharing an `ArrayList` between listener and test | Race conditions or visibility issues | Use `BlockingQueue`, `AtomicReference`, or a thread-safe collection. |
| Not closing consumers | Thread/connection leaks affecting later tests | Use try-with-resources or lifecycle cleanup. |

## 21. Comprehensive Exercise: Testing OrderCreatedListener

Build an integration test for the `orders.created` topic and a listener that updates order status.

Requirements:

1. Run a broker using EmbeddedKafka or Testcontainers.
2. Create a test listener recording events into a `BlockingQueue` or `AtomicReference`.
3. Send an event with `KafkaTemplate` and await producer acknowledgment with a timeout.
4. Use Awaitility to wait until the listener receives the matching event ID.
5. Use Awaitility to wait until the database has the order in `CREATED` status.
6. Write a test using `BlockingQueue.poll(timeout)` instead of Awaitility.
7. Write a direct consumer test, subscribing and waiting for assignment before sending records.
8. Create a `pollUntilCount` helper with a finite deadline.
9. Verify topic, key, value, partition, offset, and headers.
10. Verify the committed offset using `AdminClient`.
11. Simulate a listener retry that succeeds and wait for the expected final outcome.
12. Simulate exhausted retries and wait for the record in the DLT.
13. Use a dedicated group ID to avoid reading offsets from a previous test run.
14. Try running tests in parallel and ensure topics, event IDs, and capture state do not collide.
15. Verify tests do not use `Thread.sleep` and have no unbounded poll loops.

The exercise is complete when tests finish only after the real condition is met or a finite timeout expires, while failure messages include enough context to identify the topic, group, event, and slow processing step.

## 22. Learning Path and Completion Criteria

| Stage | Core Focus | Self-Check Criteria |
|---|---|---|
| 1. Async flow | Producer, broker, consumer, listener | Distinguish send acknowledgment from listener completion. |
| 2. Awaitility | `until` and `untilAsserted` | Wait for final state with a timeout. |
| 3. Thread safety | Queue, latch, atomic holder | Share results safely between listener and test. |
| 4. Producer future | `CompletableFuture` | Verify broker acknowledgment separately. |
| 5. Consumer polling | `poll(Duration)` | Read records using a poll loop with a deadline. |
| 6. Assignment | Subscribe and group join | Wait for partition assignment before sending when needed. |
| 7. Side effects | Database and committed offset | Wait for the exact state being verified. |
| 8. Error paths | Retry and DLT | Wait for recovery outcomes. |
| 9. Isolation | Topic, group ID, and cleanup | Avoid stale data or overlap between tests. |
| 10. Reliability | Timeouts and diagnostics | No fixed sleeps or infinite waits. |

This lesson is complete when you can choose Awaitility to wait for asynchronous state, use `BlockingQueue`/`CountDownLatch` for listener signals, or poll `KafkaConsumer` directly against a deadline. You should also be able to distinguish broker acknowledgment, listener completion, database commit, and consumer offset commit.

Kafka tests stay stable when tests wait for real conditions rather than guessing timings. Set finite timeouts, use thread-safe state, isolate topics/group IDs, and poll `KafkaConsumer` from a single thread. That way tests remain fast when the system responds promptly and fail clearly when the messaging flow does not complete.

