# Headers containing correlation id

A Correlation ID is an identifier used to link messages and operations belonging to the same request or workflow across multiple services. In Kafka, this identifier can be propagated via a record header so producers, consumers, and downstream services can log, trace, and correlate processing steps without embedding operational metadata into the business payload.

A correlation ID should be created at the first ingress point if the request does not already have a valid one, and then preserved as events travel through topics and services. Each event still has its own `eventId`; the correlation ID only groups events belonging to the same business flow. A correlation ID is also not synonymous with a distributed tracing trace ID.

## 1. What problem does Correlation ID solve?

A workflow can pass through multiple services and multiple topics:

```text
HTTP request
    |
    | correlation-id = c-7f91
    v
Order service
    |
    | orders.created
    v
Kafka
    |
    v
Inventory service
    |
    | inventory.reserved
    v
Kafka
    |
    v
Payment service
    |
    | payment.authorized
    v
Kafka
    |
    v
Notification service
```

If every event in the workflow carries the same correlation ID `c-7f91`, operators can search logs across services by the same value to reconstruct the request's path. Without this identifier, investigations often have to rely on timestamps, business keys, or payload contents; those methods are hard to rely on accurately when many requests run concurrently.

Correlation ID is useful for:

- Linking logs between producer, consumer, and downstream services.
- Tracking a workflow spanning multiple topics.
- Correlating a request with events produced from that request.
- Supporting investigations of retries, duplicates, timeouts, and DLTs.
- Finding related messages when a workflow partially fails.

Correlation ID is metadata for observability and correlation. It does not guarantee exactly-once processing, does not replace an idempotency key, and is not an authentication mechanism.

## 2. Why place the correlation ID in a Kafka header?

A Kafka record has a key, value, timestamp, and headers. Headers are a collection of name/value pairs, where the name is a string and the value is a byte array. Headers are well-suited for transport metadata such as correlation ID, trace context, source service, or schema-related metadata.

| Location | When appropriate |
| --- | --- |
| Kafka header | Metadata for tracing, logging, routing, or transport mechanics |
| Payload | Business data that the consumer needs to understand the event and run business logic |
| Kafka key | Identifier used for partitioning, per-key ordering, or log compaction |

Example of a record:

```text
topic: orders.created
key:   order-42
value: { "eventId": "evt-1001", "orderId": "order-42" }
header:
  correlation-id: "c-7f91"
```

Consumers do not need to modify the payload schema just to add a tracking identifier. However, if the correlation ID has business meaning that consumers must persist durably or display to users, consider including it in the payload per the event contract rather than relying solely on headers.

## 3. Distinguishing correlation ID, event ID, causation ID, and trace ID

These identifiers have different scopes:

| Identifier | Meaning | Lifecycle |
| --- | --- | --- |
| `correlation-id` | Groups messages belonging to the same request/workflow | Usually preserved across multiple services and topics |
| `eventId` | Unique identifier of a single event | Each new event has its own ID |
| `causationId` | Identifies the event that directly caused the current event | Changes according to causal relationships |
| `traceId` | Distributed trace identifier consisting of multiple spans | Managed by the tracing system |
| `spanId` | Identifier of a single operation/span within a trace | Each span has its own ID |

For example, an order creation request has correlation ID `c-7f91`. The Order service emits `OrderCreated` with `eventId=evt-1`. The Inventory service receives that event and emits `InventoryReserved` with `eventId=evt-2`, `causationId=evt-1`; both events still carry `correlation-id=c-7f91`.

Do not use an event ID as the correlation ID for an entire workflow if the workflow produces multiple events. Also do not generate a new trace ID for every message if tracing context needs to continue across Kafka boundaries.

## 4. Header naming convention and encoding

Choose a stable header name for the system's correlation metadata, for example:

```text
correlation-id
```

A Kafka header value is `byte[]`, so producer and consumer must agree on encoding. UTF-8 is the common choice for UUIDs or identifier strings:

```java
byte[] value = correlationId.getBytes(StandardCharsets.UTF_8);
```

When reading:

```java
String correlationId = new String(value, StandardCharsets.UTF_8);
```

Do not use `new String(bytes)` relying on the JVM's default charset; doing so can cause services in different environments to decode differently.

Kafka header names are case-sensitive. Standardize on one casing and do not let one producer send `Correlation-Id` and another send `correlation-id`, forcing consumers to guess multiple variants.

## 5. Creating the correlation ID at the first ingress point

The correlation ID is usually extracted from an HTTP gateway request header or generated when the system accepts a new workflow. If accepting an ID sent by a caller, validate its format and length before putting it into Kafka/logs.

Example utility:

```java
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIds {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    private CorrelationIds() {
    }

    public static String resolveOrCreate(String supplied) {
        if (supplied == null || supplied.isBlank()) {
            return UUID.randomUUID().toString();
        }

        String candidate = supplied.trim();
        if (!SAFE_ID.matcher(candidate).matches()) {
            throw new IllegalArgumentException("Invalid correlation id");
        }

        return candidate;
    }
}
```

The pattern above is an illustrative convention; if the system uses ULIDs or another format, adjust the allowlist and length limit accordingly. Do not accept unbounded arbitrary strings because they can bloat headers/logs or inject control characters into logs.

If the request comes from outside, a caller-supplied correlation ID is untrusted metadata. A valid ID may be kept to help correlate the request, but never use it to determine identity, access permissions, or sensitive business decisions.

## 6. Attaching correlation ID to ProducerRecord

With `KafkaTemplate`, the direct and explicit way is to create a `ProducerRecord`, add a `RecordHeader`, and send that record:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private static final String CORRELATION_ID = "correlation-id";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event, String correlationId) {
        ProducerRecord<String, OrderCreatedEvent> record =
                new ProducerRecord<>(
                        "orders.created",
                        event.orderId(),
                        event);

        record.headers().add(new RecordHeader(
                CORRELATION_ID,
                correlationId.getBytes(StandardCharsets.UTF_8)));

        kafkaTemplate.send(record);
    }
}
```

The example assumes `OrderCreatedEvent` has an `orderId()` method. The correlation ID should be resolved/validated before calling the publisher. `KafkaTemplate.send()` returns a future; if the caller needs to know whether the broker acknowledged it, observe the future/callback rather than treating the method call itself as proof of successful delivery.

If using `Message<?>` and `KafkaTemplate.send(Message<?>)`, verify that `KafkaHeaderMapper` maps the custom header to a Kafka record header according to the expected convention. When exact control over byte values and header names is needed, `ProducerRecord` is transparent.

## 7. Reading correlation ID in ConsumerRecord

A listener can receive `ConsumerRecord` to access headers directly:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private static final String CORRELATION_ID = "correlation-id";

    @KafkaListener(topics = "orders.created", groupId = "inventory-service")
    public void onMessage(ConsumerRecord<String, OrderCreatedEvent> record) {
        Header header = record.headers().lastHeader(CORRELATION_ID);

        String correlationId = header == null || header.value() == null
                ? "missing"
                : new String(header.value(), StandardCharsets.UTF_8);

        // Invoke application service with the checked correlationId.
    }
}
```

`lastHeader(name)` returns the last header with that name. If the header does not exist or its value is `null`, the listener needs a clear policy: generate a fallback ID for legacy flows, increment a missing-header metric, or reject/quarantine the record if required by contract. Never let a `NullPointerException` happen unexpectedly in business logic.

After reading, validate the format/length before putting the ID into logs or forwarding it. Records arriving from Kafka may be produced by another producer; do not assume every header is valid.

## 8. Preserving correlation ID when publishing downstream events

When a consumer processes an event and publishes the next event, forward the workflow's correlation ID. Do not generate a new UUID at every service, or the correlation chain will break.

```java
@Component
public class OrderCreatedListener {

    private static final String CORRELATION_ID = "correlation-id";

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderCreatedListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders.created", groupId = "inventory-service")
    public void onMessage(ConsumerRecord<String, String> input) {
        String correlationId = readAndValidateCorrelationId(input);
        String result = "reserved:" + input.value();

        ProducerRecord<String, String> output = new ProducerRecord<>(
                "inventory.reserved",
                input.key(),
                result);

        output.headers().add(new RecordHeader(
                CORRELATION_ID,
                correlationId.getBytes(StandardCharsets.UTF_8)));

        kafkaTemplate.send(output);
    }

    private String readAndValidateCorrelationId(
            ConsumerRecord<String, String> record) {
        Header header = record.headers().lastHeader(CORRELATION_ID);
        if (header == null || header.value() == null) {
            throw new IllegalArgumentException("Missing correlation-id header");
        }

        String value = new String(header.value(), StandardCharsets.UTF_8);
        if (value.isBlank() || value.length() > 128) {
            throw new IllegalArgumentException("Invalid correlation-id header");
        }
        return value;
    }
}
```

The example demonstrates propagating the ID across one hop; in production, reuse a shared validation utility, handle exceptions via an error handler, and do not emit output if the input contract is invalid. If other headers need to be preserved, selectively copy allowed headers rather than accidentally losing required metadata or forwarding inappropriate internal headers.

## 9. Kafka allows multiple headers with the same name

Kafka `Headers` allows multiple headers with the same name. For example, a record could contain two `correlation-id` entries due to a producer or interceptor adding duplicates. When reading via `lastHeader()`, the consumer gets the last value; `headers(name)` APIs allow iterating over all headers with the same name.

Define a clear policy:

- Each record has only one canonical correlation ID.
- If multiple distinct values are received, reject/quarantine or apply an explicit rule; do not let different services pick different values.
- When creating a new record, you can remove old headers with the same name and add a single validated value.
- Do not concatenate multiple correlation IDs into one string unless there is a contract for multi-workflow relationships.

Example normalizing the header before sending:

```java
private static void replaceCorrelationId(Headers headers, String id) {
    headers.remove("correlation-id");
    headers.add(new RecordHeader(
            "correlation-id",
            id.getBytes(StandardCharsets.UTF_8)));
}
```

Only use `remove()` when the producer genuinely intends to replace the canonical header. If the record contains other metadata, do not clear all headers.

## 10. Distinguishing business correlation ID and Spring Kafka request/reply

Spring Kafka has headers dedicated to request/reply, including `KafkaHeaders.CORRELATION_ID`, `KafkaHeaders.REPLY_TOPIC`, and `KafkaHeaders.REPLY_PARTITION`. `ReplyingKafkaTemplate` uses correlation metadata to match a reply with a pending request.

This is a framework request/reply purpose. If the application uses `ReplyingKafkaTemplate`, do not arbitrarily overwrite or remove the correlation header that the template uses to match responses. A business correlation ID used across workflows can be stored in a separate header such as `correlation-id` to avoid confusion with the request/reply matching mechanism.

| Header | Purpose |
| --- | --- |
| `correlation-id` (custom) | Links workflows/requests across the system |
| `KafkaHeaders.CORRELATION_ID` | Spring Kafka metadata used to correlate requests and replies |
| `KafkaHeaders.REPLY_TOPIC` | Topic to which the responder sends replies |
| `KafkaHeaders.REPLY_PARTITION` | Reply partition if specified |

If a project intentionally uses `KafkaHeaders.CORRELATION_ID` as the business correlation ID, clearly agree on how it is managed with `ReplyingKafkaTemplate` and all participating producers/consumers.

## 11. Correlation ID does not replace distributed tracing

Distributed tracing follows requests through spans, recording parent-child relationships and execution durations. W3C Trace Context typically transmits `traceparent` and `tracestate` headers; baggage can propagate additional context per tracing policy.

A correlation ID is usually a business workflow identifier that can outlive a single trace. For example, an order may generate events over several minutes or hours, creating different traces across consumers/retries; those events can still retain the same correlation ID.

| Criterion | Correlation ID | Trace ID |
| --- | --- | --- |
| Scope | Business request/workflow | A single distributed trace |
| Goal | Link events/logs by workflow | Analyze spans, latency, and dependencies |
| Lifecycle | Can span across multiple traces | Follows the trace context lifecycle |
| Management | Application contract | Tracing instrumentation/system |

When using Micrometer Tracing or compatible OpenTelemetry instrumentation, context propagation can automatically inject/extract trace headers when sending/receiving Kafka records. Do not manually generate `traceparent` if the tracing layer already manages context, as that can break parent-child relationships.

A record can carry both a business `correlation-id` and trace context simultaneously. The two metadata types complement each other.

## 12. Putting correlation ID into logs with MDC

Mapped Diagnostic Context (MDC) helps the logger automatically attach the correlation ID to every log line on the current thread. In a listener, set and clear MDC inside `try/finally` because consumer threads are reused across multiple records.

```java
@KafkaListener(topics = "orders.created", groupId = "inventory-service")
public void onMessage(ConsumerRecord<String, String> record) {
    String correlationId = readCorrelationId(record);
    String previous = MDC.get("correlationId");
    MDC.put("correlationId", correlationId);

    try {
        log.info("Processing order event, topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
        orderService.process(record.value());
    }
    finally {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }
}
```

The example assumes a logger and `readCorrelationId()` are already declared. Restoring the previous MDC value avoids overwriting outer context if the listener is invoked inside an existing execution context.

MDC is typically thread-local based. If the listener hands work off to an executor or `@Async`, MDC does not automatically propagate to other threads in all configurations. Pass the correlation ID as an explicit parameter or configure appropriate context propagation. Do not rely on MDC as storage for business data.

## 13. Using correlation ID in retries and DLTs

Correlation ID is especially useful when a record passes through retry topics or a dead-letter topic. Preserve the correlation ID across retries so logs of the initial attempt, retries, and DLT still belong to the same workflow.

When configuring error handlers/recoverers:

- Verify the `correlation-id` header is preserved when publishing to retry/DLT.
- If creating a new record, copy the validated correlation ID into the target record.
- Preserve original metadata such as topic, partition, offset, and exception per DLT conventions.
- Do not generate a new correlation ID just because a record is moved to a retry topic.
- When replaying a DLT after hours or days, explicitly decide whether to keep the old correlation ID to continue investigation or create a new correlation ID for a separate replay workflow; if needed, store both as `original-correlation-id` and `replay-correlation-id`.

Correlation ID helps search logs but does not automatically deduplicate retries. Use event ID/idempotency keys and appropriate transaction semantics to control side effects.

## 14. Correlation ID in fan-out and long-running workflows

One event can trigger multiple downstream events. If all belong to the same request, they can keep the same correlation ID:

```text
OrderCreated (corr=c-7f91, event=evt-1)
       |
       +----> InventoryCheck (corr=c-7f91, event=evt-2)
       |
       +----> FraudCheck     (corr=c-7f91, event=evt-3)
       |
       +----> CustomerNotify (corr=c-7f91, event=evt-4)
```

Each event has its own `eventId` and may have its own `causationId`. The shared correlation ID groups workflow branches; `causationId` identifies the event that directly caused another event.

For workflows spanning multiple days, consider correlation ID uniqueness scope and log/observability backend retention policies. Avoid reusing a single correlation ID for independent workflows.

## 15. Security and limits of correlation headers

Kafka headers are record data. They are transmitted with the record and can be read by consumers; do not treat headers as a secret area.

Principles:

- Never put passwords, access tokens, session cookies, or private data into correlation headers.
- Restrict length and allowed characters.
- Never use caller-supplied correlation IDs for authentication or authorization.
- Be careful when logging externally supplied values; strip control characters and prevent log injection.
- Do not use correlation ID as a high-cardinality metric label; use logs/traces for detailed lookups and aggregate metrics by service/topic/result.
- Define retention and log access permissions because correlation IDs can link multiple activities of the same user/workflow.

TLS protects headers in transit, but does not turn headers into secrets or guarantee that only trusted services could have created that value.

## 16. Testing correlation ID

Integration tests should verify both attaching the header at the producer and preserving it across a consumer-forwarder:

1. Send a record with a specific correlation ID.
2. Consume with a test consumer and verify header bytes decode as UTF-8 to the expected value.
3. Have the listener publish output to another topic.
4. Consume the output and verify the correlation ID remains intact.
5. Send a record without the header and verify the fallback/validation policy.
6. Send empty, oversized, invalid-character, or duplicate headers to test handling.
7. Verify MDC is cleared/restored after the listener completes or throws an exception.
8. If using retry/DLT, verify the correlation ID exists on retry/DLT records.

Example assertion:

```java
Header header = received.headers().lastHeader("correlation-id");

assertThat(header).isNotNull();
assertThat(new String(header.value(), StandardCharsets.UTF_8))
        .isEqualTo(expectedCorrelationId);
```

Do not just mock `KafkaTemplate` and verify the method was called. Integration tests with a broker verify that headers are actually serialized, stored on the record, and read back properly.

## 17. Common pitfalls

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| First service log has ID, later service does not | Consumer does not read or downstream producer does not copy header | Standardize read/write helpers and test each hop |
| Correlation ID changes at each service | Every consumer generates a new UUID | Only create at ingress when missing; preserve on subsequent hops |
| Header decodes with garbled characters | Producer/consumer use different charsets | Explicitly enforce UTF-8 |
| Header has multiple values | Multiple interceptors or code paths add the header | Define one canonical value and handle duplicates |
| Log has correlation ID from previous message | MDC is not cleared when listener thread is reused | Use `try/finally` to restore/remove MDC |
| `ReplyingKafkaTemplate` does not receive matching reply | Framework correlation header was overwritten or removed | Preserve `KafkaHeaders.CORRELATION_ID` managed by request/reply flow |
| Traces do not link despite identical correlation ID | Trace context `traceparent` is not propagated | Configure tracing instrumentation; do not confuse trace ID with correlation ID |
| DLT lacks correlation ID | Recoverer creates a new record without copying custom headers | Check DLT recoverer/header mapper and test in practice |
| Correlation ID bloats logs/metrics | ID used as metric tag or unbounded values accepted | Cap length; do not use ID as a high-cardinality label |

## 18. Implementation checklist

- [ ] Choose a stable header name, e.g., `correlation-id`.
- [ ] Use UTF-8 for header values.
- [ ] Create an ID at ingress when a request lacks a valid ID.
- [ ] Validate length and characters of externally supplied IDs.
- [ ] Preserve the correlation ID across services/topics.
- [ ] Give each event its own `eventId`; use `causationId` if causal relationships are needed.
- [ ] Distinguish correlation ID from trace ID and Spring request/reply correlation headers.
- [ ] Copy the header when publishing output, retry, or DLT records.
- [ ] Set and clean up MDC inside `try/finally`.
- [ ] Never put secrets/PII into headers.
- [ ] Do not use correlation ID as a high-cardinality metric label.
- [ ] Have integration tests checking header propagation across hops.

## 19. Conclusion

Correlation ID in Kafka headers links records belonging to the same request or workflow across multiple producers, consumers, and topics. Create the ID at the first ingress point if missing, validate the value, encode with UTF-8, and preserve it when publishing downstream events. Each event still needs its own event ID; causation ID describes causality, while trace ID is managed by distributed tracing.

In Spring Kafka, you can add headers using `ProducerRecord`/`RecordHeader` and read them with `ConsumerRecord.headers()`. If using `ReplyingKafkaTemplate`, respect `KafkaHeaders.CORRELATION_ID` reserved for request/reply; business correlation can use a dedicated header. Combine with MDC to include the ID in logs while always cleaning up context on consumer threads. Correlation ID supports observability and investigation, and does not replace idempotency, authorization, or distributed tracing.

## References

- [Apache Kafka — Record Headers API](https://kafka.apache.org/40/javadoc/org/apache/kafka/common/header/Headers.html)
- [Apache Kafka — ProducerRecord API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/ProducerRecord.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Request/Reply](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html#replying-template)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
