# Dead-letter Headers

When a record cannot be processed successfully and is moved to a **Dead Letter Topic (DLT)**, keeping only the key and value is not enough. The system must also preserve *where the record came from, why it failed, on which attempt it failed, and how it should be handled*. In Spring Kafka, this information is typically carried in **Kafka headers** added by `DeadLetterPublishingRecoverer` when publishing the record to the DLT.

Dead-letter headers are an essential part of reliability operations: they allow on-call engineers to distinguish data errors from dependency failures, link a DLT record back to its source topic/partition/offset, determine the root cause, and run a controlled replay. However, headers are only metadata; a record sitting in a DLT does not prove the business operation completed.

## 1. Context: from listener failure to DLT

A consumer can fail due to an invalid payload, missing schema, database timeout, business rule violation, or an exception in code. Once allowed retry attempts are exhausted, the recovery mechanism can move the record to a dedicated topic:

~~~text
orders [partition 2, offset 418]
            |
            v
    Order listener processes
            |
            +-- Succeeded -------------> commit progress
            |
            +-- Failed
                    |
                    v
             Error handler
                    |
             Retry + backoff
                    |
             Retry budget exhausted
                    |
                    v
        DeadLetterPublishingRecoverer
                    |
                    +-- Copy appropriate key/value
                    +-- Add source metadata
                    +-- Add exception metadata
                    +-- Optionally add custom headers
                    |
                    v
             orders.DLT
~~~

In **non-transactional** listeners, `DefaultErrorHandler` typically coordinates backoff, exception classification, and the recoverer. For listeners inside a Kafka transaction, the rollback and recovery path may use `DefaultAfterRollbackProcessor`. Both can involve a DLT, though their configuration and commit boundaries differ.

Questions to answer when inspecting a DLT record:

- Which source topic, partition, offset, and consumer group did it come from?
- Which headers indicate the exception, root cause, and stack trace?
- Are the key/value the original data, or were they altered by deserialization/conversion?
- Which metadata supports correlation, idempotency, and replay?
- Is this a retriable failure or does it require fixing data/code?
- How many times has the record passed through retry topics or DLTs?

That is why dead-letter headers are not just a serialization detail—they are part of the **recovery contract** between the application and operations.

## 2. What is a header in Kafka?

A Kafka record contains: topic, partition, offset (assigned by the broker), timestamp, key, value, and a collection of **headers**. Each header is a name and `byte[]` value pair.

Conceptual example:

~~~text
Topic: orders.DLT
Partition: 2
Offset (on DLT): 127
Key: order-901
Value: {"eventId":"evt-901","orderId":"order-901", ...}

Headers:
  event-id                     = evt-901
  kafka_dlt-original-topic     = orders
  kafka_dlt-original-partition = [binary integer: 2]
  kafka_dlt-original-offset    = [binary long: 418]
  kafka_dlt-exception-fqcn     = com.example.InvalidOrderException
  kafka_dlt-exception-message  = unsupported order state
~~~

The names above illustrate headers that Spring Kafka sets via constants; do not hard-code prefix strings when the Java API provides `KafkaHeaders` constants. Numeric types are typically binary-encoded per framework conventions, not numeric strings readable as UTF-8.

Kafka **allows multiple headers with the same key**. Therefore, when a record is forwarded across multiple steps, know whether you are reading the first or last header. `Headers.lastHeader(name)` returns the last value for that name; `Headers.headers(name)` iterates through all values sharing that name.

## 3. Source record tracing headers

`DeadLetterPublishingRecoverer` can attach source headers using constants in `KafkaHeaders`:

| Header constant | Stored info | Operational use |
|---|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Original topic | Identifies the stream where the error occurred |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition of the original record | Traces ordering and position |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset in the original topic | Correlates records or audit entries |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Timestamp of the original record | Investigates when the event occurred |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE` | Source timestamp type | Distinguishes create time vs. log append time |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group that received the record before recovery | Identifies the responsible consumer |

For example, a record read at `orders-2@418` is written to `orders.DLT-2@127`. Offset `127` on the DLT topic is a **new offset**; it does not replace source offset `418`. The `DLT_ORIGINAL_OFFSET` header links these two positions.

When multiple consumer groups read the same source topic, `DLT_ORIGINAL_CONSUMER_GROUP` helps identify **which group** routed the record to the DLT. Different groups can process the same original record with different outcomes; do not assume all consumers failed just because one DLT contains the record.

The presence of certain headers depends on the Spring Kafka version, recoverer configuration, and publish path. Operational code should handle missing headers gracefully, especially when reading older DLT records created before a framework upgrade.

## 4. Exception description headers

The second group stores information about the failure that triggered recovery.

| Header constant | Contents |
|---|---|
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Fully qualified exception class name |
| `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Inner cause class type if present |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Diagnostic stack trace |
| Headers for **key deserialization failure** in supported versions | Exception details corresponding to the key |

Example:

~~~text
DLT_EXCEPTION_FQCN  = org.springframework.kafka.listener.ListenerExecutionFailedException
DLT_EXCEPTION_CAUSE_FQCN = com.example.orders.UnsupportedOrderVersionException
DLT_EXCEPTION_MESSAGE = Unsupported order version: 9
DLT_EXCEPTION_STACKTRACE = java.lang... (multi-line)
~~~

The outer exception may be a wrapper created by the listener adapter, while the inner cause is the real business error. Therefore, to classify causes, inspect the exception FQCN, cause, and message together; do not rely solely on substring matching on the message.

Stack traces are valuable when investigating unexpected bugs, yet they can be long. They increase record size and may contain source code paths, class names, sensitive messages, or data that should not be broadly exposed. Never treat all stack trace content as safe to publish openly.

The representation and exact list of exception headers can vary across Spring Kafka versions. In code, use the constants and APIs from your project's version, and never assume every DLT record carries all headers.

## 5. Reading headers with the right data types

Because a header value is a `byte[]`, decoding depends on the data type. Strings like topic and exception FQCN can typically be read as UTF-8; partition and offset are typically binary-encoded.

Example utility for reading basic metadata:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaders;

public final class DltHeaderReader {

    private DltHeaderReader() {
    }

    public static String text(Headers headers, String name) {
        Header header = headers.lastHeader(name);
        return header == null || header.value() == null
                ? null
                : new String(header.value(), StandardCharsets.UTF_8);
    }

    public static Integer originalPartition(Headers headers) {
        Header header = headers.lastHeader(KafkaHeaders.DLT_ORIGINAL_PARTITION);
        if (header == null || header.value() == null
                || header.value().length != Integer.BYTES) {
            return null;
        }
        return ByteBuffer.wrap(header.value()).getInt();
    }

    public static Long originalOffset(Headers headers) {
        Header header = headers.lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET);
        if (header == null || header.value() == null
                || header.value().length != Long.BYTES) {
            return null;
        }
        return ByteBuffer.wrap(header.value()).getLong();
    }
}
~~~

A listener reading DLT records:

~~~java
@KafkaListener(
    topics = "orders.DLT",
    groupId = "orders-dlt-operations"
)
public void inspectDlt(ConsumerRecord<String, byte[]> record) {
    Headers headers = record.headers();

    String originTopic = DltHeaderReader.text(
            headers, KafkaHeaders.DLT_ORIGINAL_TOPIC);
    Integer originPartition = DltHeaderReader.originalPartition(headers);
    Long originOffset = DltHeaderReader.originalOffset(headers);
    String errorType = DltHeaderReader.text(
            headers, KafkaHeaders.DLT_EXCEPTION_FQCN);

    log.warn(
        "DLT record received: origin={}-{}@{} dlt={}-{}@{} error={}",
        originTopic, originPartition, originOffset,
        record.topic(), record.partition(), record.offset(),
        errorType
    );

    dltCaseService.storeForReview(record);
}
~~~

The example chooses `byte[]` for the value to illustrate raw payload handling. The DLT consumer factory must use a compatible deserializer; if using JSON-to-object, the listener parameter may be a different type. Data saved via `storeForReview` must be persisted durably with an explicit offset-acknowledgement policy.

**Do not** decode `DLT_ORIGINAL_OFFSET` with `Long.parseLong(new String(bytes))` if it was written as a binary long. Wrong decoding can yield nonsense offsets or exceptions in DLT tooling.

## 6. Configuring DeadLetterPublishingRecoverer

A common way to produce DLT headers is using `DeadLetterPublishingRecoverer` as the recoverer for `DefaultErrorHandler`.

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );
}

@Bean
DefaultErrorHandler orderErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

    handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class,
        UnsupportedOrderVersionException.class
    );

    return handler;
}
~~~

The recoverer is responsible for constructing the destination producer record, forwarding the appropriate key/value, carrying over record headers, and attaching recovery metadata. The default destination is typically the source topic plus `.DLT` with the matching partition, though a destination resolver can customize this logic as shown above.

To use the handler, attach it to the container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    return factory;
}
~~~

The DLT topic must exist or the application must have an appropriate provisioning mechanism. If routing preserves the source partition, the DLT topic must have at least the corresponding partition count; otherwise, publishing may fail. You can configure a different destination resolver to let the Kafka producer choose the partition when a 1:1 mapping is not needed.

## 7. Adding custom headers for business operations

Default headers explain **origin** and **exception**, but often are not enough for operating across multiple systems. Useful additional headers may include:

- `event-id`: stable business event identifier across retries and replays.
- `correlation-id` or `trace-id`: links logs across producers, consumers, and dependencies.
- `schema-version` or `event-type`: helps route to the right team or handler.
- `x-failure-category`: normalized error group, such as `TRANSIENT`, `VALIDATION`, `BUSINESS_RULE`.
- `x-recovery-policy`: describes the decision, such as `DLT`, `MANUAL_REVIEW`, or `DISCARD_APPROVED`.

Spring Kafka provides mechanisms to add headers on the recoverer, such as `addHeadersFunction(...)` in supported versions:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);

    recoverer.addHeadersFunction((record, exception) -> {
        var headers = new RecordHeaders();

        headers.add(
            "x-failure-category",
            failureCategory(exception).getBytes(StandardCharsets.UTF_8)
        );

        headers.add(
            "x-recovery-policy",
            "DLT".getBytes(StandardCharsets.UTF_8)
        );

        return headers;
    });

    return recoverer;
}

private static String failureCategory(Exception exception) {
    Throwable cause = exception;
    while (cause.getCause() != null) {
        cause = cause.getCause();
    }
    if (cause instanceof IllegalArgumentException) {
        return "VALIDATION";
    }
    return "UNKNOWN";
}
~~~

`failureCategory(...)` here is only a minimal example. In production, build a classifier based on business exceptions and context; do not assume every `IllegalArgumentException` is a permanent data error.

Depending on version, Spring Kafka offers APIs to customize header functions, generate exception headers, or manage existing headers. Avoid configuring custom headers with names colliding with `KafkaHeaders.DLT_*` without a clear purpose, as framework-generated source metadata could be overwritten or duplicated.

## 8. Which headers should be preserved?

When forwarding a record to a retry topic or DLT, existing Kafka headers are normally carried over per framework and recoverer policy. However, not every header should be retained forever:

| Header type | What to do? | Reason |
|---|---|---|
| `event-id`, `correlation-id` | Keep if needed for tracing and deduplication | Supports safe replay |
| `event-type`, `schema-version` | Keep when carrying business value | Restores the right record type |
| `DLT_ORIGINAL_*` | Keep initial origin per policy | Traces back to initial topic/partition/offset |
| Exception FQCN/message | Keep enough to investigate | Error classification |
| Stack trace | Weigh size and sensitivity | Can be huge or contain details that should not spread |
| Authentication token/cookie | Do not forward automatically unless needed | Prevents credential leakage |
| Single-request internal headers | Consider stripping | Avoids unnecessary contracts |

When designing event producers, avoid putting bearer tokens, session cookies, or personal data into Kafka headers in the first place. DLTs often have longer retention and broader operator read access than the main topic.

Any system consuming DLT headers as an API must explicitly specify required/optional lists, encodings, and behavior for missing or duplicate headers. Never assume `KafkaHeaders` is an immutable schema across all versions without verifying compatibility.

## 9. Headers can repeat across multiple recovery layers

An event can pass through the source topic, retry topics, a DLT, and a replay. When that happens, some source or exception headers may appear multiple times or be replaced.

~~~text
orders                 -> orders-retry-1000
orders-retry-1000      -> orders-retry-2000
orders-retry-2000      -> orders.DLT
orders.DLT (replay)    -> orders
~~~

If every step appends `DLT_EXCEPTION_MESSAGE` without dropping prior entries, the record can grow in size and contain messages from different failure events. If every forward overwrites the original topic with the immediately preceding topic, operational tooling risks mistaking a retry topic for the source topic.

Spring Kafka provides settings on the recoverer for appending original headers and stripping previous exception headers in applicable versions. Rather than relying on a fixed default, check your Spring Kafka version and decide:

1. Do you want to store the *initial source* or the *most recent hop*?
2. Do you want to keep the *latest exception* or the *entire exception history*?
3. Should each attempt be traced via separate logs/traces instead of stuffing everything into Kafka headers?
4. What are the record size limits and security requirements for error metadata?

A helpful rule: keep a durable `event-id` across all retries/replays while recording topic-hop history in your observability system. DLT headers should suffice for investigating the current record, not serve as an unbounded audit trail.

## 10. Exception headers and ErrorHandlingDeserializer

Errors can occur before the listener receives a Java object, such as unparseable JSON or a key/value deserializer failure. If the exception is thrown directly inside `poll()`, a normal listener never receives an object to handle on its own.

Spring Kafka's `ErrorHandlingDeserializer` wraps the delegate deserializer and conveys error details through headers for the container/error handler to process. Example:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

The exception headers from `ErrorHandlingDeserializer` and the `KafkaHeaders.DLT_EXCEPTION_*` group are not identical sets. Deserializer headers inform the error handler that decoding failed; the recoverer uses that information to build the DLT record and appropriate diagnostic headers.

When value deserialization fails, the payload sent to the DLT may be the **original `byte[]`**, not an `OrderEvent` object. The DLT producer needs serializers capable of writing the actual runtime types. If the application only configured `JsonSerializer<OrderEvent>`, publishing raw bytes may fail or produce unexpected output. You can use a type-based serializer or `DelegatingByTypeSerializer` in suitable configurations.

In addition, some versions provide dedicated headers for **key deserialization** failures. If a key fails, relying on the key for routing or idempotency may be unreliable. In DLT consumers, handle null keys, raw-byte keys, or unidentifiable business IDs rather than assuming the key was parsed into a valid string.

## 11. Header size and Kafka record limits

A stack trace can occupy tens of KB. If a record accumulates old headers across retries, its size grows steadily. Consequences can include:

- Producer fails to send the record due to exceeding request/record size limits.
- Broker rejects the record due to topic/broker message-size policy.
- Network bandwidth and storage for retries/DLTs increase.
- Operational tools read the DLT slowly and logs bloat.
- Sensitive error details get replicated across multiple topics.

Consider the total size of **key + value + headers + overhead**, not just the JSON payload size. Limits typically relate to producer `max.request.size` and broker/topic message size, while actual size depends on serialization and compression.

An approach when stack traces are too large:

1. Keep the exception type, a safely shortened message, and source headers.
2. Write the full stack trace to a secured logging/tracing backend with suitable retention.
3. Put the trace/correlation ID in a custom header to link the two systems.
4. Customize exception header creation using APIs supported by your version if you need to bound or omit oversized parts.
5. Never lose fields mandatory for replay, such as event ID and original topic/partition/offset.

Do not blindly truncate raw header bytes by slicing mid-UTF-8 string or mid-binary integer/long. If bounding size, re-encode cleanly according to the data type and preserve a clear contract.

## 12. DLT headers do not replace offsets and acknowledgements

When a record from `orders` is published to `orders.DLT`, the DLT entry receives a new offset. Whether the original consumer advances its offset depends on the handler, ack mode, transactions, and recovery outcome.

Some scenarios:

| Scenario | Expected outcome |
|---|---|
| DLT publish succeeds; recovery is considered complete | Source consumer may advance offset per policy |
| DLT publish fails | Do not silently treat the record as recovered |
| Process crashes after DLT publish, before source offset commit | Source record may be re-read, creating a DLT duplicate |
| DLT consumer reprocesses and crashes before committing DLT offset | DLT record may be redelivered |
| Replay from DLT to business topic | System must guard against duplicate side effects |

Dead-letter headers help detect duplicates via event ID or source coordinates, but they do not perform deduplication automatically. If the application has side effects outside Kafka, use an idempotency key, an inbox table with a unique constraint, or a durable state workflow.

Example investigation key you can use:

~~~text
consumerGroup + originalTopic + originalPartition + originalOffset
~~~

This key is useful for spotting when the same Kafka delivery was recovered multiple times. However, if the same business event was produced as multiple distinct records, you need an offset-independent `event-id` to deduplicate by business semantics.

## 13. Designing the DLT consumer and review workflow

A DLT consumer should focus on **storing, alerting, classifying, and supporting replay**, not necessarily auto-resending records to the source topic upon receipt.

An operational flow:

~~~mermaid
flowchart TD
    A["Record in DLT"] --> B["Read dead-letter headers"]
    B --> C{"Source metadata complete?"}
    C -->|No| D["Quarantine + investigate"]
    C -->|Yes| E["Classify root cause"]
    E --> F{"Issue resolved?"}
    F -->|No| G["Hold record / ticket / alert"]
    F -->|Yes| H["Approve replay"]
    H --> I["Replay keeping event-id and trace"]
    I --> J["Monitor outcome and deduplicate"]
~~~

A governance case might store fields like:

~~~json
{
  "eventId": "evt-901",
  "originalTopic": "orders",
  "originalPartition": 2,
  "originalOffset": 418,
  "dltTopic": "orders.DLT",
  "dltPartition": 2,
  "dltOffset": 127,
  "exceptionClass": "com.example.InvalidOrderException",
  "failureCategory": "VALIDATION",
  "status": "WAITING_FOR_REVIEW"
}
~~~

`dltOffset` differs from `originalOffset`; storing both links the two separate logs. For sensitive payloads, store payloads under restricted access or store only a reference/checksum rather than dumping all details into public tickets.

If DLT reading tools see missing source headers, do not fill in defaults like partition 0 or offset 0, as that fabricates evidence. Flag metadata as incomplete and route it for investigation.

## 14. Replay and preserving provenance

Replay must answer: where is the record republished from the DLT, which key, timestamp, event ID, and headers must be kept, and is there a risk of business duplication?

Principles:

- Keep `event-id` and correlation IDs to enable deduplication.
- Distinguish the topic being replayed to from the initial source topic.
- Avoid copying the entire old exception stack trace back into the business stream if consumers do not need it.
- Add dedicated replay metadata, such as `x-replay-id`, `x-replayed-at`, `x-replay-operator`, if security policy allows.
- Only replay after resolving the root cause or establishing loop-prevention safeguards.
- Never alter offset/partition headers to pretend a record came from a different origin.
- Verify compatible serializers, especially when the DLT record holds raw bytes from a deserialization failure.

Illustrative handling flow:

~~~text
DLT record:
  event-id = evt-901
  original-topic = orders
  exception = UnsupportedOrderVersionException

After upgrading consumer:
  republish event-id = evt-901 to orders
  add x-replay-id = replay-2026-11-15-001
  store audit: originalTopic/partition/offset + replay ID
~~~

When republished to Kafka, the record receives a new offset on the destination topic. `DLT_ORIGINAL_*` headers can be kept in an audit store, but should not replace the current metadata assigned by the Kafka broker.

## 15. Security and privacy of dead-letter headers

A DLT is not a harmless zone. Exception headers can reveal service names, internal file paths, SQL errors, endpoint URLs, or snippets of payload data appearing in exception messages. DLTs are often retained longer for investigation, so they need dedicated policies:

1. Restrict DLT read/write ACLs strictly to applications and operational teams that truly need them.
2. Define retention and deletion capabilities per data classification.
3. Never put credentials, tokens, or secrets into Kafka headers.
4. Sanitize exception messages if exceptions might include user data.
5. Never copy full stack traces into broadly accessible alerts, tickets, or dashboards.
6. Maintain an audit trail for replay actions, especially on payment or order streams.

To share error metadata with monitoring systems, exception class, event type, retry count, original topic, and correlation ID are usually enough. Full stack traces belong in a logging backend with proper access control.

## 16. Observability driven by DLT headers

Using source and exception headers, the system can build dashboards broken down by failure category:

| Metric | Meaning |
|---|---|
| DLT record count by original topic | Which stream is generating failures |
| DLT record count by exception class | Which error category is rising |
| DLT record count by consumer group | Which consumer needs attention |
| Rate of missing original metadata | Detects header compatibility/configuration issues |
| Age of unresolved DLT records | Recovery backlog |
| Replay success/failure rate | Effectiveness of remediation workflow |
| Replay count for same event ID | Risk of loops or duplicate effects |
| DLT record/header size | Detects stack trace/metadata bloat |

Use exception class, topic, event type, or error category as metric labels with relatively low cardinality. Do not use event ID or original offset as Prometheus/Micrometer metric labels, because each event creates a new time series. Those identifiers belong in searchable logs or traces.

A concise log:

~~~text
DLT_RECEIVED origin=orders-2@418
  consumerGroup=order-projection
  error=UnsupportedOrderVersionException
  eventId=evt-901
  dlt=orders.DLT-2@127
  action=MANUAL_REVIEW
~~~

This log suffices for initial triage without printing raw payloads or stack traces. When deeper detail is needed, authorized operators can look up by event ID or trace ID.

## 17. Runbook for anomalous dead-letter headers

### Missing original topic/partition/offset

- Determine whether the record was actually published by `DeadLetterPublishingRecoverer` or by another custom producer.
- Check the Spring Kafka version and header-creation/retention configuration.
- Check if the record was replayed or forwarded through an intermediate tool that stripped headers.
- Do not guess the source from the DLT name if the topology uses custom routing; flag missing metadata and investigate via audit/traces.

### Exception message present but cause unclear

- Read `DLT_EXCEPTION_FQCN`, cause FQCN if available, and stack trace per access permissions.
- Check wrapper exceptions such as `ListenerExecutionFailedException`.
- Use explicit business exception types in the listener for more stable classification.

### Multiple copies of the same header

- Check whether the record passed through multiple retry/recovery hops or was replayed.
- Use `lastHeader` when only the latest value is needed; use `headers(name)` when all values are needed.
- Verify the recoverer's append/strip policy in your running version.
- Avoid repeatedly accumulating stack traces on each forward.

### DLT publish fails on records with many headers

- Check total record size against producer/broker/topic limits.
- Check serializers for raw bytes or objects.
- Consider trimming exception metadata using supported customization hooks.
- Ensure the handler does not treat a failed publish as successful recovery.

### Replay hits the same error again

- Compare the current exception class against the prior DLT record.
- Verify whether the dependency or schema was genuinely fixed.
- Verify the event ID remained intact and deduplication works.
- Pause bulk replay to avoid creating a DLT loop.

## 18. Dead-letter headers design checklist

- [ ] DLT records carry sufficient source metadata: topic, partition, offset, and consumer group when available.
- [ ] Exception FQCN, cause, and message are readable under your actual framework/version.
- [ ] Numeric headers are decoded as binary integers/longs, not UTF-8 strings.
- [ ] Custom headers use clear names and never accidentally overwrite `KafkaHeaders.DLT_*` constants.
- [ ] Event ID stays intact across retries, DLT, and replay.
- [ ] A policy exists for duplicate headers and multi-hop forwards.
- [ ] Stack traces/exception messages neither leak secrets nor exceed record size limits.
- [ ] The DLT producer can serialize both original payloads and raw bytes on deserialization errors.
- [ ] Failed recovery publishes are never treated as successful handling.
- [ ] The DLT consumer persists cases/audits before acknowledging progress per policy.
- [ ] Replays are controlled, idempotent, and preserve provenance.
- [ ] Dashboards/alerts track DLT volume, errors, record age, and replay status.

**Dead-letter headers turn a DLT from a bucket of failed records into an investigable, recoverable data source.** In Spring Kafka, build on `KafkaHeaders.DLT_*`, `DeadLetterPublishingRecoverer`, and stable business metadata to preserve origin, interpret exceptions, and run safe replays. Never let oversized headers or inconsistent encoding turn the recovery path itself into a new source of failures.
