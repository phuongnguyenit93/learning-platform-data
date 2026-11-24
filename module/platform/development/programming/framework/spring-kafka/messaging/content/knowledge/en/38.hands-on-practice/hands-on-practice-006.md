# Adding Retry and Dead-Letter Handling

In this hands-on lab, we complete the `orders` pipeline: the producer sends events to the source topic, the consumer processes them with `@KafkaListener`, Spring Kafka automatically retries on transient errors, and sends records to a dead-letter topic (DLT) when retries are exhausted or when an error should not be retried. We will verify both the case where processing succeeds after retries and the case where a record must be isolated.

This lab uses blocking retry with `DefaultErrorHandler`. While a record is being retried, subsequent records in the same partition must wait. If the business workflow needs to keep processing newer records while a failed record waits for a long delay, evaluate non-blocking retry with `@RetryableTopic` and accept the ordering trade-offs.

## 1. Objectives and Processing Flow

Once completed, the application will be able to:

- Send `OrderCreated` to the `orders` topic using `KafkaTemplate`.
- Retry up to two times after the initial attempt, with a one-second interval between attempts.
- Route `InvalidOrderException` straight to the DLT without retrying.
- Route transient errors that persist after retries to `orders.DLT`.
- Verify that DLT records preserve the key, payload, and source metadata for investigation.

```mermaid
flowchart TD
    A[Producer: KafkaTemplate] --> B[orders topic]
    B --> C[@KafkaListener]
    C --> D{Processing succeeded?}
    D -->|Yes| E[Complete and commit offset per AckMode]
    D -->|No| F{Non-retryable error?}
    F -->|Yes| H[DeadLetterPublishingRecoverer]
    F -->|No| G{Retries left?}
    G -->|Yes| I[BackOff 1 second then redeliver]
    I --> C
    G -->|Exhausted| H
    H --> J[orders.DLT topic]
    J --> K[DLT consumer / investigation workflow]
```

## 2. Adding Dependencies

If the project does not yet include Spring Kafka, add the `spring-kafka` library. The test dependency `spring-kafka-test` is used for Embedded Kafka at the end. When using Spring Boot, let Boot's dependency management align compatible versions:

```kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

Spring Boot dependency management/BOM can manage compatible versions for these two dependencies. Do not arbitrarily mix Kafka client and Spring Kafka versions.

## 3. Preparing the Source Topic and DLT

The example uses a source topic `orders` with three partitions. The DLT also needs at least three partitions because the configuration below preserves the source record's partition number when routing to the DLT.

```java
@Bean
NewTopic ordersTopic() {
    return TopicBuilder.name("orders")
        .partitions(3)
        .replicas(1)
        .build();
}

@Bean
NewTopic ordersDltTopic() {
    return TopicBuilder.name("orders.DLT")
        .partitions(3)
        .replicas(1)
        .build();
}
```

A replication factor of `1` suits a local broker or single-node Embedded Kafka. In real environments, provision topics via administrative tools and set replication factor, `min.insync.replicas`, retention, and ACLs according to cluster standards. The consumer's runtime principal does not necessarily need topic-creation permissions.

If no custom resolver is declared, `DeadLetterPublishingRecoverer` also defaults to routing to a topic with the `.DLT` suffix and matching partition. An explicit example in the configuration makes the rule used by the application clear.

## 4. Configuring Producer and Consumer

For JSON events, the producer uses `JsonSerializer` and the consumer uses `JsonDeserializer`. Example Spring Boot configuration:

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer
spring.kafka.producer.acks=all

spring.kafka.consumer.group-id=orders-service
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties.spring.json.trusted.packages=com.example.orders
```

`auto-offset-reset=earliest` only takes effect when the group has no valid committed offset yet. In production, explicitly decide the offset policy and trusted packages; never open trusted packages wider than needed. The example assumes the event class resides in package `com.example.orders`.

## 5. Creating the Event and Classifying Exceptions

Use an event with an order ID and sufficient data for processing. Java record example:

```java
public record OrderCreated(
    String orderId,
    BigDecimal amount,
    String currency
) {}
```

Separate permanent data errors from transient dependency failures:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class TransientOrderException extends RuntimeException {
    public TransientOrderException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

`InvalidOrderException` represents an event that cannot be processed unless the data changes, such as a negative amount or unsupported currency. `TransientOrderException` represents a potentially self-healing issue, such as a temporary timeout in a pricing service. Classify by business cause rather than simply by whether an exception is checked or runtime.

## 6. Writing the Listener and Letting Exceptions Propagate

The listener only coordinates business processing. When the service throws an exception, do not catch it, log it, and return normally; the container would treat the record as successfully processed and commit the offset according to `AckMode`.

```java
@Component
public class OrderListener {
    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
    public void consume(OrderCreated event) {
        orderService.process(event);
    }
}
```

In `OrderService`, validate data and invoke dependencies. For example, throw `InvalidOrderException` if the event is invalid; throw `TransientOrderException` while preserving the root cause if a dependency is temporarily unavailable. The listener does not need to write its own retry loop.

```java
public void process(OrderCreated event) {
    if (event.amount().signum() <= 0) {
        throw new InvalidOrderException("Order amount must be positive");
    }
    try {
        pricingClient.verify(event.orderId(), event.amount(), event.currency());
        orderRepository.save(event);
    } catch (PricingTimeoutException ex) {
        throw new TransientOrderException("Pricing service timed out", ex);
    }
}
```

`PricingTimeoutException`, `pricingClient`, and `orderRepository` represent application components. In real code, only translate recoverable dependency failures into `TransientOrderException`; data or business-rule errors must preserve their corresponding non-retryable exception types.

## 7. Configuring DefaultErrorHandler and the DLT Recoverer

`DefaultErrorHandler` accepts a `BackOff` and a recoverer. `FixedBackOff(1_000L, 2L)` means waiting one second between retries and allowing two retries after the initial processing attempt. The total number of times the listener can be invoked is three.

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {
        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()));

        // Do not treat DLT send as successful if the broker reports an error.
        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer, new FixedBackOff(1_000L, 2L));

        handler.addNotRetryableExceptions(InvalidOrderException.class);
        handler.addRetryableExceptions(TransientOrderException.class);
        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler ordersErrorHandler) {
        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
```

Ensure the `KafkaTemplate` used by the recoverer has serializers compatible with the key/value of records sent to the DLT. For JSON events, the template must be able to send the payload type the consumer actually receives. If handling deserialization errors, the payload may be a raw byte array; in that case, configure a template supporting both byte arrays and domain types or use an appropriate serialization strategy.

The resolver in the example constructs the DLT name by appending `.DLT` to the source topic and keeping the same partition. Therefore, `orders.DLT` must have enough matching partitions. If the source topic has partition 2 while the DLT only has one partition, publishing can fail; do not assume Kafka automatically remaps the partition to a valid one.

## 8. Wiring the Producer and Sending Events

The producer sends events with `orderId` as the key. Records for the same order are therefore routed consistently to the same partition of the `orders` topic by the default partitioner:

```java
@Service
public class OrderPublisher {
    private final KafkaTemplate<Object, Object> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<Object, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<Object, Object>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "orders", event.orderId(), event);
    }
}
```

In Spring Kafka 3.x and later, `send()` returns a `CompletableFuture`; tests can wait on the future to confirm the producer received an acknowledgment. Spring Kafka 2.x uses `ListenableFuture` and its corresponding callbacks. In production flows, handle the future asynchronously and log send failures; do not block business threads waiting for send results unnecessarily.

## 9. Reading and Investigating Records in the DLT

A separate consumer can monitor the DLT. Use a distinct group ID so the DLT inspection consumer does not interfere with the group processing the source topic:

```java
@KafkaListener(topics = "orders.DLT", groupId = "orders-dlt-audit")
public void inspectDeadLetter(ConsumerRecord<String, OrderCreated> record) {
    log.warn(
        "Dead letter received: topic={}, partition={}, offset={}, key={}",
        record.topic(), record.partition(), record.offset(), record.key());

    // Headers can be inspected to extract source topic/partition/offset and exception details.
    record.headers().forEach(header ->
        log.debug("DLT metadata header: {}", header.key()));
}
```

`DeadLetterPublishingRecoverer` attaches headers to trace the source topic, partition, offset, and exception details. When logging or auditing, avoid writing full sensitive payloads or secrets. The DLT is for isolation and investigation; it does not automatically repair data or replay records.

When replay is needed, fix the root cause first, verify the event is still valid against current business state, and then replay through a controlled process. Keep event IDs stable and design idempotent consumers because replays can cause redeliveries.

## 10. Understanding Retry and Offset Behavior Precisely

With `FixedBackOff(1_000L, 2L)` configured, processing behaves as follows:

| Error type | Max listener invocations | Outcome |
| --- | ---: | --- |
| Succeeds immediately | 1 | Does not enter DLT |
| `TransientOrderException`, succeeds on third attempt | 3 | Continues normal processing |
| `TransientOrderException`, fails all three attempts | 3 | Recoverer sends to `orders.DLT` |
| `InvalidOrderException` | 1 | Skips retries and goes straight to DLT |

This is blocking retry: the failing record holds the head of the partition while retrying. Subsequent records in the same partition wait until the failing record succeeds or recovery finishes. Other partitions can still be processed by other consumers.

When DLT recovery publishing succeeds, the error handler can proceed according to the container's acknowledgment/commit policy. If DLT publishing fails and `setFailIfSendResultIsError(true)` reports an error, recovery is not treated as successful; the record may be reprocessed. Therefore monitor DLT send failures as well, not just listener errors.

## 11. Testing with Embedded Kafka

Add `spring-kafka-test` in test scope and spin up a broker with both the source topic and the DLT. Use three partitions for both topics to match the resolver:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders", "orders.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrdersRetryIntegrationTest {
    @Autowired
    KafkaTemplate<Object, Object> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void invalidOrderIsPublishedToDlt() throws Exception {
        Map<String, Object> props = KafkaTestUtils.consumerProps(
            "dlt-check-" + UUID.randomUUID(), "false", embeddedKafka);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (Consumer<String, byte[]> dltConsumer =
                new DefaultKafkaConsumerFactory<>(
                    props, new StringDeserializer(),
                    new ByteArrayDeserializer()).createConsumer()) {
            embeddedKafka.consumeFromAnEmbeddedTopic(
                dltConsumer, "orders.DLT");

            OrderCreated invalid = new OrderCreated(
                "order-invalid", new BigDecimal("-10.00"), "VND");
            kafkaTemplate.send("orders", invalid.orderId(), invalid)
                .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, byte[]> deadLetter =
                KafkaTestUtils.getSingleRecord(dltConsumer, "orders.DLT");
            assertThat(deadLetter.key()).isEqualTo("order-invalid");
            assertThat(deadLetter.value()).isNotEmpty();
            assertThat(deadLetter.headers().toArray()).isNotEmpty();
        }
    }
}
```

The test consumer uses `ByteArrayDeserializer` to read raw DLT payloads without depending on JSON type headers. In your project, add the corresponding imports and assertion library. `getSingleRecord` waits for a record within the helper's default timeout; if the test suite produces multiple DLT records, use a dedicated topic per test or poll and filter by key.

Add the following test cases:

- Valid event is processed once and does not appear in the DLT.
- Mocked dependency fails twice then succeeds on the third attempt; listener is invoked three times with no DLT record.
- Dependency fails continuously; record appears in the DLT after the third attempt.
- `InvalidOrderException` goes to the DLT immediately after the first attempt without waiting for backoff.
- DLT broker/topic unavailable; verify recovery fails and the source offset is not committed as if recovered.
- DLT record carries the right key, payload, and source metadata headers.

## 12. Operations and Troubleshooting

Monitor retry counts, listener failures, DLT record counts, DLT publish errors, consumer lag, and the age of the oldest record in the DLT. When DLT volume spikes, group by exception type and source topic to find the root cause: unreachable dependency, malformed payload, or code bug.

Common scenarios:

| Symptom | What to check |
| --- | --- |
| Record retries continuously | Whether the exception is classified properly; whether backoff and retry count are appropriate. |
| No records appear in DLT | Whether the recoverer is attached to the right factory; whether the DLT topic exists with matching partition count. |
| DLT send fails | Template serializer, `WRITE` ACL, broker connectivity, and target topic. |
| Subsequent records are delayed | Blocking retry is holding the partition; consider shorter backoff or non-blocking retry if ordering allows. |
| Replay causes duplicate side effects | Use stable event IDs and business-level idempotency. |

The DLT needs retention long enough for investigation, plus a workflow to process and clean up data. Never bulk-replay before fixing the root cause, as records will simply bounce back to the DLT and create a loop.

## 13. Lab Completion Checklist

- [ ] Create `orders` and `orders.DLT` topics with compatible partition counts.
- [ ] Configure JSON serializer/deserializer for the event.
- [ ] Create the listener and let exceptions propagate to the error handler.
- [ ] Attach `DefaultErrorHandler` to the right listener container factory.
- [ ] Configure two retries with a one-second backoff.
- [ ] Classify `InvalidOrderException` as non-retryable.
- [ ] Configure `DeadLetterPublishingRecoverer` and verify send results.
- [ ] Inspect DLT metadata and controlled replay procedures.
- [ ] Run integration tests for success, retry success, retry exhausted, and non-retryable failure.
- [ ] Monitor retries, DLT, lag, and recovery errors in the runtime environment.

The lab is complete when a valid event flows through the source topic and succeeds, transient errors are retried within bounds, permanent data errors go straight to the DLT, and persistent errors go to the DLT once retries are exhausted. Combining bounded retries, send-verified recoverers, timely offset commits, and idempotency allows a Spring Kafka pipeline to recover from failures while preserving traceability.
