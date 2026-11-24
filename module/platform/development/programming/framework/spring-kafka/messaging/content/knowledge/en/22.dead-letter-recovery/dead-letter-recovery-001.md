# What Is a Dead-Letter Topic?

In a Kafka stream, there are records that cannot be processed successfully even after the consumer retries according to policy. For example, a malformed payload, data that violates business rules, or a dependency error that has exceeded the allowed number of retries. Keeping that record in the main flow can cause the consumer to repeatedly hit the same error and slow down subsequent records.

A **dead-letter topic (DLT)** is a separate Kafka topic used to store failed records that have been moved out of the main processing flow. A DLT allows the consumer to continue processing normal data while the development team retains the payload along with metadata about its source and failure reason for later investigation, data repair, or replay.

A DLT is not a special topic type defined by Kafka. It is a regular Kafka topic used by applications and Spring Kafka by convention to store failed records. Therefore, a DLT must be created, authorized, configured for retention, monitored, and operated just like any other topic.

## 1. Why Do We Need a Dead-Letter Topic?

Suppose a consumer reads from the `orders.events` topic. A record with an invalid `orderId` causes the listener to throw an exception. If the record is always retried without limit, the consumer may be unable to advance to subsequent records on that partition. If the record is skipped without being saved, the operations team loses the data needed to investigate and remediate the issue.

A DLT solves this problem by routing the failed record to another topic after the retry policy is exhausted or when the error is classified as non-retryable.

```text
orders.events
      |
      v
  @KafkaListener
      |
      +---- processing succeeds -------------------> commit per AckMode
      |
      +---- processing fails
                |
                v
        Exception classification
                |
          +-----+------+
          |            |
       Retryable    Non-retryable
          |            |
       BackOff         |
          |            |
       Retry           |
          |            |
     Retries exhausted |
          +-----+------+
                |
                v
       DeadLetterPublishingRecoverer
                |
                v
          orders.events.DLT
                |
                v
       Investigate / fix / replay
```

When the recoverer transfers the record successfully, the error handler can acknowledge the source record as handled according to the acknowledgement mode and commit configuration. If publishing to the DLT fails, that error must be reported and handled according to policy, avoiding marking the source record as recovered when the DLT copy has not been persisted.

## 2. What Information Does a DLT Contain?

Typically, a record sent to a DLT preserves the key and payload of the original record, while adding headers that describe its origin and the error.

| Component | Meaning |
|---|---|
| Key | Key of the source record, if present |
| Value | Original payload or raw bytes depending on the serialization/deserialization path |
| Original topic | Topic where the record failed |
| Original partition | Source partition |
| Original offset | Offset of the source record |
| Original timestamp | Timestamp of the source record, if present |
| Exception class | Name of the exception class that caused the failure |
| Exception message | Error message |
| Exception stack trace | Stack trace for diagnostics, if configured to be recorded in headers |
| Consumer group | Group that processed the source record, if corresponding metadata is available |

Spring Kafka uses headers with conventional names, such as `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, `KafkaHeaders.DLT_EXCEPTION_FQCN`, and `KafkaHeaders.DLT_EXCEPTION_MESSAGE`. The exact headers depend on the version and recoverer in use.

Source metadata is crucial when tracing a record back. A DLT record has a new offset in the DLT topic; that offset is not its original offset in the source topic. Use the original topic/partition/offset headers to locate where the failure occurred.

## 3. How Does a DLT Differ from a Retry Topic?

Both a retry topic and a DLT are regular Kafka topics, but they serve different purposes:

| Criterion | Retry topic | Dead-letter topic |
|---|---|---|
| Purpose | Hold records to retry processing after a waiting period | Store records whose retries are exhausted or that are non-retryable |
| When moved in | When an error is allowed to retry under a non-blocking policy | When retries are exhausted or the exception is non-retryable |
| Next processing | Retry consumer reads the record again | Humans or a DLT handling flow investigate and decide the next step |
| Desired outcome | Return to normal business processing | Isolate failures so they do not block the main flow |

With blocking retry, `DefaultErrorHandler` typically seeks the consumer back to the failed record and retries in place. Once retries are exhausted, the recoverer can send the record to the DLT. With non-blocking retry, `@RetryableTopic` creates retry topics according to backoff settings and moves the record to the DLT when attempts are exhausted.

A DLT does not replace retries. Retries are suited for transient errors that can recover on their own; a DLT is suited for isolating records that still cannot be processed after the configured policy.

## 4. How Does Spring Kafka Send Records to a DLT?

For record listeners, Spring Kafka commonly combines `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`:

- `DefaultErrorHandler` receives exceptions from the listener.
- The exception classifier decides whether the error is retryable.
- `BackOff` defines the wait interval and number of retries.
- When recovery is needed, `DeadLetterPublishingRecoverer` creates a new record and publishes it to the DLT.

Configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        recoverer.setFailIfSendResultIsError(true);

        var backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

In this example, the consumer attempts to process the initial record and then has up to two retries, waiting one second between attempts. If it still fails, the recoverer publishes the record to the DLT. `setFailIfSendResultIsError(true)` instructs the recoverer to report an error if the DLT send result fails; verify the API against your project's Spring Kafka version.

Attaching the handler to the container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
```

Listener using that factory:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void consume(OrderEvent event) {
        orderService.process(event);
    }
}
```

The `OrderEvent` class, `orderService`, and serializer/deserializer configuration are part of the illustrative application. If a listener uses a different container factory, `DefaultErrorHandler` must be attached to that exact factory.

## 5. DLT Naming and Default Routing

When using `new DeadLetterPublishingRecoverer(kafkaTemplate)` without providing a custom destination resolver, Spring Kafka routes records by default to a topic with the `.DLT` suffix and the partition matching the source partition.

Example:

```text
orders.events, partition 2, offset 105
             |
             | recover
             v
orders.events.DLT, partition 2
```

Because the recoverer preserves the corresponding partition by default, the target partition must exist on the DLT topic. The simplest approach is to create the DLT with at least as many partitions as the source topic. If the source topic has six partitions, for instance, the DLT should also have at least six partitions.

You can create the topic using Spring Kafka's `TopicBuilder`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class DeadLetterTopicConfiguration {

    @Bean
    NewTopic ordersDeadLetterTopic() {
        return TopicBuilder.name("orders.events.DLT")
                .partitions(6)
                .replicas(1)
                .build();
    }
}
```

A replication factor of `1` in the example is only suitable for local or demo environments. In production, choose replication factor, min ISR, and retention according to durability, capacity, and operational policies. If the cluster does not enable auto topic creation, create the DLT before any failed records are published.

### Customizing the destination resolver

You can route to a DLT using your own convention, such as changing the suffix or grouping errors by topic category:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

var recoverer = new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
                record.topic() + ".dead-letter",
                record.partition()
        )
);
```

If routing to a different partition or consolidating multiple source topics into a single DLT, ensure the target partition is valid and that source metadata remains sufficient for tracing. Avoid picking a partition with an arbitrary modulo operation without accounting for target partition count and business ordering.

## 6. DLT for Non-Retryable Exceptions and Exhausted Retries

Two common cases cause a record to be sent to a DLT:

1. **Non-retryable exception:** a data error or business error that cannot self-recover on retry, such as `InvalidOrderException`.
2. **Retry exhausted:** an initially retryable error that still fails after exceeding the configured retry count or duration.

You can declare non-retryable exceptions on `DefaultErrorHandler`:

```java
handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        IllegalArgumentException.class
);
```

Other errors continue to use the configured retry/backoff policy. After the recoverer sends to the DLT successfully, the container handles offset commits according to the acknowledgement mode and error handler settings. If publishing to the DLT fails, the recoverer should report the error so the source record is not mistakenly acknowledged as successfully transferred.

Do not treat the DLT as a place to immediately send every error. If a dependency only loses connectivity for a few seconds, retrying with backoff can recover the record without manual intervention.

## 7. DLT When Using @RetryableTopic

Spring Kafka supports non-blocking retries via `@RetryableTopic`. This annotation configures retry topics and a DLT for a listener. After a record exhausts all attempts, the framework moves it to the DLT.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    private static final Logger log = LoggerFactory.getLogger(PaymentListener.class);

    private final PaymentService paymentService;

    PaymentListener(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0),
            dltTopicSuffix = ".DLT"
    )
    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(PaymentEvent event) {
        paymentService.process(event);
    }

    @DltHandler
    public void handleDlt(PaymentEvent event) {
        log.error("Payment event moved to DLT: paymentId={}", event.paymentId());
    }
}
```

In this example, `attempts = "4"` represents the total number of attempts, including the initial processing attempt. When attempts are exhausted, the record is moved to the `payments.events.DLT` topic per the configured suffix. If no suffix is declared, `@RetryableTopic` uses its own default convention (typically `-dlt`), which differs from the `.DLT` suffix of the default `DeadLetterPublishingRecoverer`.

`@DltHandler` is the method that receives records from the DLT in the corresponding retry topic configuration. You can use it to record, alert, or create a manual handling request. If you only need the DLT as a storage topic, you can create a separate listener reading the DLT topic instead of handling it in the same class.

Non-blocking retries can allow subsequent records to be processed ahead of a record waiting in a retry topic. If business logic requires strict ordering by key or partition, consider blocking retry and DLT rather than choosing retry topics solely because waiting does not block the main flow.

## 8. Reading and Investigating Records in a DLT

A DLT is a normal topic, so it can be read using `@KafkaListener` like any other topic. Use a dedicated consumer group for the investigation flow so it does not affect the group processing the main topic.

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
class OrderDeadLetterListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderDeadLetterListener.class);

    @KafkaListener(
            topics = "orders.events.DLT",
            groupId = "orders-dlt-inspector"
    )
    public void consume(ConsumerRecord<String, String> record) {
        String originalTopic = readHeader(record, KafkaHeaders.DLT_ORIGINAL_TOPIC);

        log.error(
                "Dead letter received: dltTopic={}, originalTopic={}, key={}, value={}",
                record.topic(),
                originalTopic,
                record.key(),
                record.value()
        );
    }

    private String readHeader(ConsumerRecord<String, String> record, String name) {
        Header header = record.headers().lastHeader(name);
        if (header == null || header.value() == null) {
            return null;
        }
        return new String(header.value(), StandardCharsets.UTF_8);
    }
}
```

When reading headers, use Spring Kafka's `KafkaHeaders.DLT_ORIGINAL_TOPIC` constant instead of typing header names manually. Actual header names are defined by Spring Kafka; use the API/constants from your project's version. Avoid logging sensitive payloads in production logs; logging ID, topic, partition, offset, and exception metadata is usually enough for tracing.

Example using Spring Kafka constants:

```java
import org.springframework.kafka.support.KafkaHeaders;

Header originalTopicHeader = record.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);
```

During investigation, record at a minimum:

- Source topic, partition, and offset.
- Consumer group that processed the record.
- Exception type, message, and stack trace if stored.
- Failure timestamp and delivery/retry count if metadata is available.
- Remediation status and the person/process executing the replay.

## 9. Serialization of the DLT Producer

DLT records are sent via a producer, so keys/values must be serializable with the producer configuration. In the normal flow, the consumer may have already deserialized the value into a Java object; the recoverer then needs a compatible serializer to send that object to the DLT.

For deserialization errors, the original payload may only remain as a byte array because the object could not be constructed. In that case, the DLT producer must support both regular object types and `byte[]` if the same recoverer handles both kinds of records. Spring Kafka can use `DelegatingByTypeSerializer` to select a serializer based on runtime type.

Conceptual configuration example:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<Class<?>, org.apache.kafka.common.serialization.Serializer<?>> delegates =
        new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(Object.class, new JsonSerializer<>());

var valueSerializer = new DelegatingByTypeSerializer(delegates);
```

This illustrates selecting a serializer by type; when configuring the actual producer factory, ensure generic types, matching order, and key/value serializers are compatible with your Spring Kafka version. If the system only processes valid JSON and does not route raw deserialization errors through the same producer, a simpler serializer can be used.

Do not assume every DLT record is an already-deserialized Java object. For corrupted data, keeping the original raw bytes is often necessary for investigation or fixing before replay.

## 10. What If Publishing to the DLT Fails?

Moving a record to the DLT is only complete when the producer sends the record successfully according to the configured acknowledgement policy. If the DLT topic does not exist, the target partition is invalid, ACLs deny access, or the broker is unavailable, publishing can fail.

Some operational principles:

1. Create the DLT and appropriate partitions before starting production consumers.
2. Grant DLT write permissions to the producer/recoverer and read permissions to the DLT consumer.
3. Configure the recoverer to fail when the send result fails, if supported by your version.
4. Monitor DLT publish failures and do not commit the source record as though recovery completed.
5. Also test scenarios where the DLT broker/topic is unavailable.

If DLT publishing fails yet the source record is still committed, the record can be lost from the processing stream with no copy for investigation. That is why you must observe the recoverer's send result and verify commit behavior according to the acknowledgement mode.

With a transactional listener, DLT publishing can be coordinated inside a Kafka transaction if the transaction manager and recoverer are configured properly. Distinguish Kafka transactions from database or HTTP side effects; DLT publishing inside a Kafka transaction does not automatically encompass resources outside Kafka.

## 11. Replaying Records from a DLT

A DLT does not automatically fix data nor automatically return records to the source topic. Once the root cause is found, you can choose one of the following approaches:

- Fix the data or schema and publish the corrected record to the business topic.
- Use a replay consumer to read the DLT and send records to the source topic or a recovery topic.
- Run a controlled replay tool, scoped by topic/partition/offset or event ID.
- Discard the record if it is confirmed to no longer have business value, while recording an audit log of the decision.

When replaying, the republished record will receive a new offset. Preserve source metadata in custom headers or audit payloads so you know which DLT and old offset it originated from.

Replaying can produce duplicate side effects. For example, the first processing attempt may have written to the database successfully before failing prior to offset commit, and then the record was routed to the DLT or replayed. The business system needs idempotency via event ID, unique constraints, upserts, or the inbox pattern to prevent creating duplicate orders/payments.

Do not bulk-replay directly into production without evaluating replay rate, consumer capacity, key ordering, and impact on downstream dependencies. Test with a small batch, verify the results, and then scale up.

## 12. DLT Retention, Security, and Monitoring

A DLT is typically retained longer than the main stream so operations teams have time to investigate, but it should not be stored indefinitely without a capacity and data plan.

Aspects to configure:

| Item | Operational question |
|---|---|
| Retention | How long should failed records be kept for investigation and replay? |
| Replication | How many replicas are needed to tolerate broker failures? |
| ACL | Which services are allowed to publish, read, and delete DLT data? |
| Encryption | Is sensitive data protected in transit and at rest? |
| Monitoring | Are DLT spikes, max record age, and publish failures alerted on? |
| Ownership | Who is responsible for investigating and deciding to replay/discard records? |

Metrics to track include the number of records routed to the DLT by topic and exception class, age of the oldest record, consumer lag of the DLT inspector, successful/failed replay counts, and DLT publish failures. A sudden spike in the DLT often signals a producer schema change, business bug, or dependency outage.

Do not log tokens, passwords, credentials, or sensitive personal data into exception messages or DLT logs unnecessarily. DLT payloads can contain original business data, so appropriate access controls and retention must be applied.

## 13. Common Misconceptions

1. **Assuming a DLT is a special Kafka topic type.** A DLT is just a regular topic used by convention.
2. **Assuming a DLT replaces retries.** Retries handle transient, self-healing errors; a DLT isolates records after retry policy exhaustion or non-retryable errors.
3. **Assuming a successful DLT send means the payload is fixed.** A DLT only stores the record and failure metadata for investigation or replay.
4. **Assuming the offset on the DLT is the source offset.** DLT records receive a new offset; read the original offset headers.
5. **Failing to create enough partitions for the DLT.** The default resolver may preserve the source partition, so the target partition must exist.
6. **Assuming every DLT uses the same suffix.** Default `DeadLetterPublishingRecoverer` and `@RetryableTopic` have different suffix conventions; configure them explicitly when consistency is needed.
7. **Ignoring DLT publish failures.** If sending to the DLT fails while the source record is still acknowledged, you can lose the record needed for investigation.
8. **Assuming replay will not cause duplicate processing.** Side effects outside Kafka may execute again; idempotency is required.
9. **Overlooking retention and security.** A DLT can hold business payloads and stack traces for a long time.

A DLT is a controlled holding area for records that cannot be processed in the main flow. In Spring Kafka, `DeadLetterPublishingRecoverer` and `@RetryableTopic` help route failed records to a dedicated topic along with metadata for tracing. A solid DLT design ensures publishes are acknowledged, partitions and serializers are compatible, investigation ownership is clear, and idempotent replay plus retention monitoring are in place.
