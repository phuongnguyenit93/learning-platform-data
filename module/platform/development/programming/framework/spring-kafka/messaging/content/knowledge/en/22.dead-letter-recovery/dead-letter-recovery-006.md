# Dead-Letter Headers

When Spring Kafka routes a failed record to a dead-letter topic (DLT), the sent record typically carries headers describing its origin and failure reason. This metadata helps operations teams identify which topic, partition, and offset the record came from, which consumer group processed it, and which exception occurred. DLT consumers can use these headers for error classification, alerting, audit logging, or planning replays.

In the `SPRING_KAFKA_MESSAGING` module, producers send events with `KafkaTemplate`, consumers process them with `@KafkaListener`, and `DeadLetterPublishingRecoverer` handles publishing the record after the retry/recovery policy decides to move it to the DLT. DLT headers are part of the operational contract: you need to understand their values, data types, potential header duplication, and any sensitive information that may appear in them.

The typed listener examples in this lesson use the following event:

```java
import java.math.BigDecimal;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total
) {}
```

## 1. What Are Dead-Letter Headers Used For?

A record moved to a DLT typically preserves its original payload and original headers while adding metadata about the source record and exception. As a result, DLT handlers do not have to guess the record's origin solely from the topic name.

Example source record:

```text
topic: orders.created
partition: 2
offset: 184
key: order-1001
value: OrderCreatedEvent(...)
```

After recovery moves the record to `orders.created.DLT`, the DLT record may carry headers like:

```text
kafka_dlt-original-topic          = orders.created
kafka_dlt-original-partition      = 2
kafka_dlt-original-offset         = 184
kafka_dlt-original-consumer-group = orders-projection
kafka_dlt-exception-fqcn          = com.acme.orders.InvalidOrderStateException
kafka_dlt-exception-message       = Order cannot be shipped before payment
```

The names shown on the wire correspond to constants in `KafkaHeaders`. When writing Spring Kafka code, prefer using those constants instead of hardcoding header string names to avoid typos.

## 2. Headers Describing the Original Record

Spring Kafka provides `KafkaHeaders.DLT_ORIGINAL_*` constants to read metadata of the original record:

| Constant | Metadata | Meaning |
|---|---|---|
| `DLT_ORIGINAL_TOPIC` | Original topic | Topic from which the record was consumed before moving to the DLT |
| `DLT_ORIGINAL_PARTITION` | Original partition | Partition containing the source record |
| `DLT_ORIGINAL_OFFSET` | Original offset | Offset of the record within the source partition |
| `DLT_ORIGINAL_TIMESTAMP` | Original timestamp | Timestamp of the source record |
| `DLT_ORIGINAL_TIMESTAMP_TYPE` | Timestamp type | Indicates whether the timestamp was producer-created or broker-appended |
| `DLT_ORIGINAL_CONSUMER_GROUP` | Original consumer group | Group that processed the record prior to recovery |

The three fields—topic, partition, and offset—are normally used together to locate the source record. An offset only has meaning within a single partition, so never use the offset alone as a global identifier.

`DLT_ORIGINAL_CONSUMER_GROUP` is especially helpful when multiple services or groups share a topic with different processing policies. It identifies which group sent the record to the DLT.

## 3. Headers Describing the Exception

`KafkaHeaders.DLT_EXCEPTION_*` headers describe the error that caused the record to be sent to the DLT:

| Constant | Meaning |
|---|---|
| `DLT_EXCEPTION_FQCN` | Fully qualified name of the exception class |
| `DLT_EXCEPTION_CAUSE_FQCN` | Class name of the root cause, if present |
| `DLT_EXCEPTION_MESSAGE` | Exception message |
| `DLT_EXCEPTION_STACKTRACE` | Stack trace as text |

These headers support error categorization and incident investigation. For instance, you can group DLT records by exception class to spot bad data, invalid business state, or transient dependency failures.

Do not use the exception message as a stable error code. Messages can change across code versions, contain input data, or vary between retries. If you need long-term classification, add a standardized error code in the payload or a custom header while keeping exception metadata for investigation.

## 4. Dedicated Headers for Key/Value Deserialization Errors

An error can occur before the listener is even called: the consumer fails to deserialize the key or value. With `ErrorHandlingDeserializer`, Spring Kafka can attach dedicated metadata for key/value deserialization errors to the record sent to the DLT.

Common header groups:

| Group | Constant | Content |
|---|---|---|
| Key deserialization | `DLT_KEY_EXCEPTION_FQCN` | Exception class when deserializing the key |
| Key deserialization | `DLT_KEY_EXCEPTION_MESSAGE` | Error message for key deserialization |
| Key deserialization | `DLT_KEY_EXCEPTION_STACKTRACE` | Stack trace for key deserialization |
| Value deserialization | `DLT_VALUE_EXCEPTION_FQCN` | Exception class when deserializing the value |
| Value deserialization | `DLT_VALUE_EXCEPTION_MESSAGE` | Error message for value deserialization |
| Value deserialization | `DLT_VALUE_EXCEPTION_STACKTRACE` | Stack trace for value deserialization |

These headers differ from `DLT_EXCEPTION_*`, which cover errors occurring during listener execution. For deserialization errors, the listener may not have received a normal Java object; the DLT consumer may need to read the payload as `byte[]` to inspect or repair the data.

If a DLT can receive both deserialized records and records retaining raw bytes from deserialization errors, the producer template used to publish to the DLT must support both value types. For example, configure a serializer by runtime type or use separate appropriate templates. Do not assume a `JsonSerializer<OrderCreatedEvent>` can handle raw `byte[]`.

## 5. Configuring `DeadLetterPublishingRecoverer`

`DeadLetterPublishingRecoverer` creates the record sent to the DLT and adds origin/exception metadata. Example routing records to a `.DLT`-suffixed topic while preserving the partition index:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Configuration
public class DeadLetterConfiguration {

    @Bean
    public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        return new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()
                )
        );
    }
}
```

The example uses `KafkaTemplate<Object, Object>` to illustrate a template that can be configured with a serializer supporting multiple payload types. In production, configure the actual serializers explicitly; in particular, support `byte[]` if the DLT receives deserialization failure records. If the DLT preserves the partition index, the DLT topic needs enough partitions to match the source topic.

You can pick another DLT naming convention, such as a shared `dead-letter-events` topic, but when multiple source topics funnel into one DLT, the `DLT_ORIGINAL_TOPIC` metadata becomes essential for routing replays back to the right source.

`DeadLetterPublishingRecoverer` can be attached to `DefaultErrorHandler` or `DefaultAfterRollbackProcessor` depending on the error-handling flow. Headers are added by the recoverer; the error handler/after-rollback processor decides when to call the recoverer.

## 6. Reading DLT Headers with `@Header`

If a DLT listener only needs certain metadata fields, they can be injected directly with `@Header`:

The following example is for records sent to the DLT due to processing errors after the payload has already deserialized into `OrderCreatedEvent`. If the DLT also holds deserialization-error records, use a listener accepting `ConsumerRecord<?, ?>` or `Message<?>` to handle payloads flexibly.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderDltListener {

    @KafkaListener(
            topics = "orders.created.DLT",
            groupId = "orders-dlt-inspector"
    )
    public void inspect(
            OrderCreatedEvent event,
            @Header(KafkaHeaders.DLT_ORIGINAL_TOPIC) String originalTopic,
            @Header(KafkaHeaders.DLT_ORIGINAL_PARTITION) Integer originalPartition,
            @Header(KafkaHeaders.DLT_ORIGINAL_OFFSET) Long originalOffset,
            @Header(name = KafkaHeaders.DLT_EXCEPTION_FQCN, required = false)
                    String exceptionType,
            @Header(name = KafkaHeaders.DLT_EXCEPTION_MESSAGE, required = false)
                    String exceptionMessage) {

        System.out.printf(
                "DLT event=%s original=%s-%d@%d exception=%s message=%s%n",
                event.eventId(),
                originalTopic,
                originalPartition,
                originalOffset,
                exceptionType,
                exceptionMessage
        );
    }
}
```

`required = false` is appropriate for optional headers such as exception messages, since certain error types or configurations may not populate every metadata field. For headers required by your application's DLT contract, you can keep the default required setting so the listener fails if metadata is missing.

The target type in `@Header` must be compatible with how the header mapper converts data. For listeners receiving `Message<?>`, headers are read from `MessageHeaders`; when reading directly from `ConsumerRecord`, Kafka headers are byte arrays and must be decoded into the appropriate types.

## 7. Reading Directly from `ConsumerRecord.headers()`

When you need to stay at the low-level Kafka API, read headers from `ConsumerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public String readStringHeader(ConsumerRecord<?, ?> record, String name) {
    Header header = record.headers().lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(header.value(), StandardCharsets.UTF_8);
}
```

Usage example:

```java
String originalTopic = readStringHeader(
        record, KafkaHeaders.DLT_ORIGINAL_TOPIC);
String exceptionType = readStringHeader(
        record, KafkaHeaders.DLT_EXCEPTION_FQCN);
```

This snippet only decodes text headers. Partition/offset headers are numeric; do not read them by blindly converting byte arrays to UTF-8. If you need to read numeric values directly from `ConsumerRecord`, follow the encoding convention produced by your Spring Kafka version or receive the header via `@Header` with the appropriate target type.

Kafka allows multiple headers with the same name. `lastHeader(name)` retrieves the last header; if you need to inspect the full header history, use `headers().headers(name)` and iterate through the list. Do not assume every record has exactly one value for a given header.

## 8. Original Headers, DLT Headers, and Custom Headers

A record moved to the DLT can carry three groups of information:

1. **Original event headers:** such as `event-type`, `correlation-id`, `traceparent` added by the producer.
2. **DLT source headers:** original topic, partition, offset, timestamp, and consumer group.
3. **Exception headers:** exception class, cause, message, and stack trace.

Custom headers should be used for metadata useful across the event lifecycle, such as correlation ID or business event ID. Avoid using headers to store full payloads or large business state.

When a record passes through multiple rounds of retry/DLT/replay, original headers may be preserved or appended depending on recoverer configuration and Spring Kafka version. If your system needs to distinguish the initial origin from the most recent DLT transfer, define clearly which headers represent each milestone and check the append/replace policy of the recoverer you use.

Do not rely on header ordering in the list as a business contract. For repeatable headers, pick `lastHeader` or iterate all entries according to agreed application semantics.

## 9. Replaying Records from DLT and the Meaning of Metadata

DLT headers help locate the original record, but they do not automatically replay it. A replay process must determine:

- Whether the record is still valid to process after the bug is fixed.
- Whether the consumer needs it sent back to the original topic or to a dedicated retry/replay topic.
- Whether to keep the key to maintain partition routing by aggregate.
- Whether to add `replay-at`, `replay-by`, or `replay-reason` for auditing.
- Whether the target consumer supports the payload's schema/type version.
- Whether the event was partially processed before failing; if so, the handler must be idempotent.

For example, the original record `orders.created-2@184` can be replayed after fixing data or the consumer. When republished, the new record gets a new topic/partition/offset. `DLT_ORIGINAL_*` describes the origin captured during dead-lettering; the broker metadata of the new publish describes the new position. These two locations are not the same.

Keep `eventId` stable across replays so the application layer can detect duplicates. When replaying via a producer, add new audit metadata rather than overwriting or spoofing the original record's offset.

## 10. Security and Header Size Limits

Exception messages and stack traces can contain sensitive details such as SQL statements, table names, payload fragments, internal URLs, tokens, or personal data. DLTs often have long retention and are accessed by many operators; therefore, DLT read access and logs must be controlled.

Guiding principles:

- Never put secrets, access tokens, or credentials into custom headers.
- Treat stack traces and exception messages as access-controlled data.
- Consider filtering or truncating exception messages before storing if they may contain sensitive data.
- Keep headers small; long stack traces inflate record size and can hit broker message/request size limits.
- Do not log full payloads and headers by default when records contain sensitive data.
- Set dedicated ACLs on DLT topics and restrict which consumer groups can read/replay them.
- Enforce DLT retention and deletion policies per your system's data governance requirements.

Headers assist diagnostics but do not replace structured logs/metrics. Log identifying fields such as original topic, partition, offset, exception class, and event ID; store full stack traces only where access controls are appropriate.

## 11. Observing and Classifying DLTs

DLT consumers or operational tools can use headers to build dashboards:

| Observed field | Question to answer |
|---|---|
| `DLT_ORIGINAL_TOPIC` | Which topic has a high rate of failed records? |
| `DLT_ORIGINAL_CONSUMER_GROUP` | Which consumer group is experiencing issues? |
| `DLT_EXCEPTION_FQCN` | Which exception type accounts for the majority? |
| `DLT_EXCEPTION_CAUSE_FQCN` | Is the root cause concentrated in a single dependency? |
| `DLT_ORIGINAL_PARTITION` | Is there a partition with an unusual concentration of errors? |
| `DLT_ORIGINAL_TIMESTAMP` | How long has the failed record been sitting in the system? |

Metrics should count DLT records by source topic, group, exception class, and time. Avoid using event IDs or exception messages as metric labels because cardinality can grow without bound. Detailed values belong in structured logs or a DLT inspection store.

## 12. Testing Dead-Letter Headers

Integration tests should verify actual headers after the recoverer publishes the record:

- Create source and DLT topics with compatible partition counts.
- Send a record with a key and a custom header like `correlation-id`.
- Make the listener throw an exception to trigger retry/recovery.
- Wait for the record to appear in the DLT.
- Read the DLT with `ConsumerRecord` and verify `DLT_ORIGINAL_TOPIC`, partition, offset, timestamp, and consumer group.
- Check `DLT_EXCEPTION_FQCN`, message, and cause according to the exception type.
- Send a deserialization-failing payload to verify key/value exception headers and raw bytes are preserved accurately.
- Forward/replay a record multiple times to verify duplicate-header or append/replace policies.
- Confirm sensitive headers are filtered according to application policy.

Use Embedded Kafka or Testcontainers to test the real flow. For DLT consumers reading with `@Header`, verify the types converted by the mapper; for `ConsumerRecord`, check the raw byte values and decode using the right convention.

## 13. Common Pitfalls

- **Looking only at the DLT payload while ignoring source metadata:** makes it hard to trace the failing topic/partition/offset and consumer group.
- **Using offset alone to locate a record:** offsets are only unique within a partition; combine with topic and partition.
- **Confusing exception headers with deserialization exception headers:** listener errors and deserialization errors use distinct metadata groups.
- **Assuming the DLT payload is always a POJO:** deserialization failures can leave raw `byte[]` in the DLT.
- **Using a serializer that does not support raw bytes:** the recoverer cannot publish deserialization-failed records to the DLT.
- **Reading numeric headers as UTF-8:** partition/offset are numeric and require proper mapping/decoding.
- **Assuming headers cannot repeat:** Kafka permits multiple headers with the same name; define how values are selected.
- **Relying on exception messages for long-term classification:** messages are unstable and may contain sensitive data.
- **Failing to restrict DLT read permissions:** stack traces and payloads can expose internal details.
- **Replaying without keeping event ID/idempotency:** can cause duplicate side effects.
- **Overwriting original metadata during replay:** destroys the ability to distinguish the source position from the new position.

## 14. Dead-Letter Headers Checklist

- [ ] DLT is configured via a recoverer matched with the error handler/after-rollback processor.
- [ ] Source metadata is read using `KafkaHeaders.DLT_ORIGINAL_*`.
- [ ] Exceptions are read using `KafkaHeaders.DLT_EXCEPTION_*`.
- [ ] Key/value deserialization headers are handled separately.
- [ ] DLT serializer supports both object payloads and raw `byte[]` if needed.
- [ ] DLT topic has appropriate partitions and retention.
- [ ] Consumers know how to read headers via `@Header`, `MessageHeaders`, or `ConsumerRecord`.
- [ ] Rules exist for duplicate headers and multiple forwarding/replay rounds.
- [ ] Replay preserves event ID and idempotency; does not spoof original offsets.
- [ ] Stack traces/messages/custom headers do not leak secrets or sensitive data.
- [ ] ACLs, retention, metrics, and DLT handling workflows are defined.
- [ ] Integration tests verify actual headers, including deserialization failures.

Dead-letter headers turn a DLT from a dumping ground for failed records into a traceable, operable source of metadata. By properly reading `DLT_ORIGINAL_*`, `DLT_EXCEPTION_*`, and key/value deserialization headers—while managing payload types, duplicate headers, and sensitive data—development teams can classify failures and perform controlled replays without losing event provenance.
