# Shared header conventions across services

## 1. Why are header conventions needed?

A Kafka record has a key, value, timestamp, and headers. The payload usually holds business data; headers carry metadata accompanying the record so services can coordinate without stuffing all transport information into the payload.

For example, an order event service can send an `OrderCreatedEvent` payload while attaching `event-id`, `event-type`, `correlation-id`, and `traceparent`. Receiving services use this metadata to identify the event, log, link processing chains, and continue distributed tracing.

If every service invents its own header names and encodings, the system easily runs into problems:

- Service A sends `eventId`, while service B looks for `event-id`, causing metadata to appear missing.
- One side writes timestamps as epoch milliseconds, while the other reads them as ISO-8601 strings.
- Headers share the same name but carry different meanings across topics.
- A service accidentally forwards internal headers or sensitive data to another service.
- When changing versions, producers and consumers do not know which headers are required or safely ignored.

Shared conventions allow producers and consumers to remain independent in language and framework while interpreting metadata under the same contract.

## 2. How do Kafka headers differ from payload and key?

Three components are frequently confused:

| Component | Role | Example |
|---|---|---|
| Key | Routes records to partitions and supports entity-ordered processing | `orderId` |
| Value/payload | Business data of the event | `OrderCreatedEvent` |
| Headers | Descriptive, tracing, and record-interpretation metadata | `event-id`, `content-type`, `correlation-id` |

Do not use headers to replace business data that consumers need for decision-making. If `orderId` is required to process an order, it must be in the payload or key per contract; do not hide it only in headers.

Headers also do not replace the Kafka key. Kafka does not use `correlation-id` or `event-id` in headers to pick partitions by default. If events for the same order must land in the same partition, set `orderId` as the record key.

Kafka headers are a list of name and byte-value pairs. A record can contain multiple headers with the same name. Header order is preserved in the record; therefore consumers must know whether a header is single-valued or multi-valued and how to choose a value if it appears multiple times.

In Spring Messaging, `Message<?>` represents headers as a map so one header name holds only one value in that map. If you need to preserve duplicate Kafka headers or control exact bytes on the wire, work directly with `ProducerRecord` and `ConsumerRecord`.

## 3. Recommended shared header convention set

There is no single mandatory set of custom header names for every Kafka system. Services within the same platform should agree on an explicit contract. The following table provides a practical convention set applicable to event streams:

| Header | Required? | Value format | Meaning |
|---|---|---|---|
| `event-id` | Yes | UUID or unique UTF-8 string ID | Identifies an event across retries and deduplication |
| `event-type` | Yes | Stable name like `order.created` | Business event type |
| `content-type` | Yes | MIME type, e.g., `application/json` | Payload format |
| `schema-version` | Yes | Version number as string, e.g., `1` | Payload schema version |
| `source` | Yes | Logical name of publishing service, e.g., `order-service` | Source that produced the event |
| `occurred-at` | Yes if business needs event time | ISO-8601/RFC 3339 UTC | Business time when the event occurred |
| `correlation-id` | Per business flow | UTF-8 string | Links multiple steps within the same workflow |
| `causation-id` | When an event originates from another event | `event-id` of the preceding event | Indicates direct cause |
| `traceparent` | When distributed tracing is used | W3C Trace Context | Carries trace context across service boundaries |
| `tracestate` | Per tracing vendor | W3C Trace Context | Additional tracing vendor state |
| `tenant-id` | Multi-tenant systems only | Tenant ID per contract | Identifies tenant if routing/context is needed |

Names in the table are system conventions, except for standard tracing names like `traceparent` and `tracestate`. If the organization already uses CloudEvents or a standard event envelope, follow the naming and bindings of that standard rather than creating a parallel header set.

### Semantics to standardize

- `event-id` is the identifier of a business event emission. When retrying the same event, keep this ID unchanged. When creating a new event, issue a new ID.
- `event-type` describes business meaning and should not contain Java class names whose packages might change.
- `schema-version` describes payload structure. Increment the version when changing contracts according to agreed compatibility rules.
- `source` should be a stable logical service name, not a pod ID or hostname that changes across deployments.
- `occurred-at` is when the business event occurred, distinct from the Kafka record timestamp which may reflect record creation or broker append time.
- `correlation-id` can be preserved throughout a workflow. It does not have to equal `trace-id`.
- `causation-id` points to the event that directly led to the current event; it differs from correlation ID which spans the whole chain.
- `traceparent` must be created and propagated by a W3C-compatible tracing propagator, never assembled manually as a string.

## 4. Naming rules and value encoding

Standardize the following rules for custom headers:

1. Use lowercase ASCII and hyphens (`kebab-case`), e.g., `event-id`, `schema-version`.
2. Header names are case-sensitive at the Kafka layer; producers and consumers must use the exact same casing.
3. Avoid spaces, accented characters, and ambiguous names like `id`, `type`, `time`, `version`.
4. Do not use framework-reserved or internal metadata prefixes like `spring_` or `__` without fully understanding framework mechanics.
5. Specify whether headers are single-valued or multi-valued. Most event metadata should be single-valued.
6. Strings are UTF-8 encoded; do not rely on the host machine's default charset.
7. Numeric values should have an explicit format. For versions, use integer strings; for timestamps, use ISO-8601 UTC.
8. Binary values must have an explicit contract for encoding and versioning; do not put arbitrary Java objects into headers.

Kafka stores header values as `byte[]`. Therefore, when writing strings, use `StandardCharsets.UTF_8`; when reading, use the same encoding. Do not convert header bytes to String using the default charset.

Example helper for creating text header values:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class EventHeaderValues {

    private EventHeaderValues() {
    }

    public static byte[] utf8(String value) {
        if (value == null) {
            throw new IllegalArgumentException("Header value must not be null");
        }
        return value.getBytes(StandardCharsets.UTF_8);
    }

    public static String asUtf8(byte[] value) {
        if (value == null) {
            throw new IllegalArgumentException("Header value must not be null");
        }
        try {
            return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(value))
                .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                "Header is not valid UTF-8", ex
            );
        }
    }
}
~~~

## 5. Attaching headers when sending with Spring Kafka

For cross-service contracts requiring explicit bytes, you can build a `ProducerRecord` and add headers directly. The example below uses `OrderCreatedEvent` as the payload; value serializer configuration must match the event type, such as a JSON serializer:

~~~java
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event,
            String correlationId,
            String traceparent) {

        ProducerRecord<String, OrderCreatedEvent> record =
            new ProducerRecord<>("orders", event.orderId(), event);

        record.headers()
            .add("event-id", EventHeaderValues.utf8(event.eventId()))
            .add("event-type", EventHeaderValues.utf8("order.created"))
            .add("content-type", EventHeaderValues.utf8("application/json"))
            .add("schema-version", EventHeaderValues.utf8("1"))
            .add("source", EventHeaderValues.utf8("order-service"))
            .add("occurred-at", EventHeaderValues.utf8(
                event.occurredAt().toString()
            ));

        if (correlationId != null) {
            record.headers().add(
                "correlation-id",
                EventHeaderValues.utf8(correlationId)
            );
        }

        if (traceparent != null) {
            record.headers().add(
                "traceparent",
                EventHeaderValues.utf8(traceparent)
            );
        }

        return kafkaTemplate.send(record);
    }
}
~~~

The example assumes `OrderCreatedEvent` has `eventId()`, `orderId()`, and `occurredAt()` methods. In real applications, `traceparent` should be obtained from the active tracing library/propagator. Do not construct trace context with arbitrary strings.

You can create a shared helper or component to avoid every publisher writing header names manually. However, the helper should only standardize names and encoding; semantics, requirement status, and value generation timing still belong to each event type's contract.

## 6. Reading and validating headers on the consumer

When exact inspection of Kafka headers is needed, accept `ConsumerRecord<K, V>`. `Headers.lastHeader(name)` returns the last header with that name; if the contract requires a single-valued header, detect and reject duplicates instead of silently picking one value.

~~~java
import java.util.Iterator;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;

public final class RequiredEventHeaders {

    private RequiredEventHeaders() {
    }

    public static String requiredSingleUtf8(
            Headers headers,
            String name) {

        Iterator<Header> values = headers.headers(name).iterator();

        if (!values.hasNext()) {
            throw new IllegalArgumentException(
                "Missing required Kafka header: " + name
            );
        }

        Header header = values.next();

        if (values.hasNext()) {
            throw new IllegalArgumentException(
                "Kafka header must not be duplicated: " + name
            );
        }

        if (header.value() == null) {
            throw new IllegalArgumentException(
                "Kafka header must not be null: " + name
            );
        }

        return EventHeaderValues.asUtf8(header.value());
    }
}
~~~

Usage in a listener:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection"
    )
    public void handle(
            ConsumerRecord<String, OrderCreatedEvent> record) {

        String eventId = RequiredEventHeaders.requiredSingleUtf8(
            record.headers(), "event-id"
        );

        String eventType = RequiredEventHeaders.requiredSingleUtf8(
            record.headers(), "event-type"
        );

        if (!"order.created".equals(eventType)) {
            throw new IllegalArgumentException(
                "Unsupported event type: " + eventType
            );
        }

        if (!eventId.equals(record.value().eventId())) {
            throw new IllegalArgumentException(
                "event-id in header does not match payload"
            );
        }

        orderProjectionService.apply(record.value());
    }
}
~~~

Validating headers before calling business logic ensures contract violations are caught at the integration boundary. For optional headers, read only when present and define clear behavior when missing. Do not turn a missing header into the string `"null"` or a default value that can mask producer bugs.

If using `@KafkaListener` annotations only, metadata can be bound via `@Header`:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(
        @Payload OrderCreatedEvent event,
        @Header("event-id") byte[] eventIdHeader,
        @Header(name = "correlation-id", required = false) byte[] correlationIdHeader) {

    String eventId = EventHeaderValues.asUtf8(eventIdHeader);
    String correlationId = correlationIdHeader == null
        ? null
        : EventHeaderValues.asUtf8(correlationIdHeader);

    orderProjectionService.apply(event, eventId, correlationId);
}
~~~

Binding via `@Header` is convenient for simple listeners, but header type conversion depends on the configured `RecordMessageConverter` and header mapper. If the contract requires strict UTF-8 byte checks, duplicate-header detection, or cardinality enforcement, accept `ConsumerRecord` and validate directly.

## 7. Using Spring Message and KafkaHeaders

Spring Kafka allows creating `Message<?>` with payload and headers. `KafkaHeaders` provides reserved header names for record-control information, such as topic and key. Business headers like `event-id` or `correlation-id` still must be defined in the application contract.

Example:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "orders")
    .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
    .setHeader("event-id", event.eventId())
    .setHeader("event-type", "order.created")
    .setHeader("schema-version", "1")
    .setHeader("correlation-id", correlationId)
    .build();

kafkaTemplate.send(message);
~~~

When using `KafkaTemplate.send(Message<?>)`, the template's `RecordMessageConverter` and header mapper participate in converting the Spring Message into a Kafka record. On the consumer side, the converter/header mapper can map Kafka headers into Spring Message headers.

Verify the corresponding serializer and converter configuration. If string headers must be written as exact UTF-8 bytes for multiple languages, verify actual bytes in integration tests or use `ProducerRecord.headers().add(...)` as shown earlier. Do not assume every Spring header is converted into bytes identically across all mapper configurations.

`KafkaHeaders.TOPIC` and `KafkaHeaders.MESSAGE_KEY` are record-control metadata. Headers like `event-id`, `event-type`, and `schema-version` are event-contract metadata. Do not name custom headers after Spring Kafka internal headers.

## 8. Headers for tracing and request correlation

Three kinds of IDs are often confused:

| Value | Scope | Used for |
|---|---|---|
| `event-id` | A single event | Deduplication and emission tracking |
| `correlation-id` | A workflow or business chain | Finding all related steps in logs |
| `traceparent` | A distributed trace | Linking spans across services per W3C Trace Context |

A workflow can emit multiple event IDs while preserving the same correlation ID. Each processing step through a service can create a new span within the same trace context. `causation-id` identifies the event that directly led to the current event.

When receiving an event and emitting a subsequent event:

- Issue a new `event-id` for the new event.
- Set `causation-id` to the incoming event's `event-id` if there is direct causality.
- Keep `correlation-id` if the new event belongs to the same workflow.
- Use a tracing propagator to inject `traceparent` and `tracestate` for the current span.
- Do not blindly copy every header from the incoming record to the new record.

If the application uses Micrometer Tracing, OpenTelemetry, or another tracing library, use the corresponding Kafka instrumentation/propagator to inject and extract trace context. Manually copying an old `traceparent` can prevent traces from reflecting the new span or corrupt parent-child relationships.

## 9. Repeatable headers and cardinality policies

Kafka allows multiple headers with the same name. For example, a record may carry multiple `tag` values:

~~~java
record.headers()
    .add("tag", EventHeaderValues.utf8("priority"))
    .add("tag", EventHeaderValues.utf8("billing"));
~~~

This is useful if the contract defines multi-valued headers. However, event-identifying headers should generally be single-valued:

| Group | Recommended cardinality | Policy |
|---|---|---|
| `event-id`, `event-type`, `schema-version`, `content-type` | Exactly one | Missing or duplicated is a contract error |
| `correlation-id`, `causation-id`, `source` | At most one | Can be required or optional depending on event type |
| `traceparent` | At most one | Per W3C Trace Context |
| `tracestate` | At most one | Content per tracing standard |
| `tag` or extension labels | Multiple allowed | Read all values in order if contract permits |

When a single-valued header is duplicated, picking `lastHeader` without validation can allow a buggy producer or intermediary component to overwrite metadata unnoticed by the consumer. For multi-valued headers, consumers must read the full list with `headers(name)` and preserve order per contract.

## 10. Versioning and evolving header contracts

Headers are part of the inter-service contract. Changing names, formats, or meanings can prevent older consumers from processing records correctly.

Apply a compatibility-oriented rollout process:

1. Add the new header as optional first.
2. Deploy consumers capable of reading both old and new formats.
3. Once new consumers are ready, producers begin sending the new header.
4. Monitor the rate of consumers reading successfully and log warnings while the old header still appears.
5. Remove the old header only after all consumers needing it have been upgraded.

Never change the meaning of an existing header under the same name. If a format change is incompatible, use a schema version or a new header name/contract version as specified. The payload's `schema-version` is not necessarily the version of the entire header contract; document the scope of each version clearly.

Consumers should ignore unknown optional headers, provided those headers do not affect decoding or security. Unknown or invalid required headers must be handled according to an explicit error policy, such as bounded retries followed by dead-letter routing for investigation.

## 11. Security and size limits

Headers are stored with the Kafka record and can be read by any consumer permitted to read the topic. Do not treat headers as a secret channel or a metadata area restricted to a single service.

Do not put the following into headers:

- Access tokens, refresh tokens, API keys, passwords, or secrets.
- Sensitive personal data unnecessary for consumers.
- Entire JSON payloads or file contents.
- Stack traces, exception messages, or internal data that could expose system structure.
- User authentication info intended merely for forwarding across services.

Transmit only the minimum metadata needed for routing, tracing, contracts, and business processing. Use TLS, topic ACLs, and proper secret management; Kafka ACLs typically control permissions at the topic level, not per individual header.

Headers also increase record size. Keep header count and value lengths small, avoiding large baggage or long JSON strings. If metadata is large, place it in the payload or store it in a suitable system and pass a reference. Total record limits remain governed by producer, broker, and consumer message/batch size configurations.

When forwarding events, use an allowlist of headers permitted for propagation. Do not copy all headers unconditionally, as that can leak internal info, tokens, or context that is no longer valid after crossing into another service.

## 12. Testing shared header contracts between services

Test contracts on both producer and consumer, not only verifying that the listener receives the payload.

**Producer tests** should verify:

- All required headers are present.
- Header names are spelled accurately and in lowercase.
- String values are UTF-8 encoded.
- `event-id`, `event-type`, `schema-version`, and `content-type` match the contract.
- Optional headers appear only when carrying valid values.
- No sensitive headers or internal headers are emitted.

**Consumer tests** should verify:

- Missing required headers are detected.
- Duplicated single-valued headers are rejected.
- Missing optional headers are handled properly.
- Wrongly encoded or malformed values are handled per policy.
- Consumers ignore unknown optional headers if the contract allows.
- Consumers remain compatible with previous producer versions during rollout.

Example unit test verifying the single-valued header reader helper:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

class RequiredEventHeadersTest {

    @Test
    void readsSingleUtf8Header() {
        var headers = new RecordHeaders();
        headers.add(
            "event-id",
            EventHeaderValues.utf8("evt-1001")
        );

        assertThat(
            RequiredEventHeaders.requiredSingleUtf8(headers, "event-id")
        ).isEqualTo("evt-1001");
    }

    @Test
    void rejectsDuplicateSingletonHeader() {
        var headers = new RecordHeaders();
        headers.add("event-id", EventHeaderValues.utf8("evt-1"));
        headers.add("event-id", EventHeaderValues.utf8("evt-2"));

        assertThatThrownBy(
            () -> RequiredEventHeaders.requiredSingleUtf8(headers, "event-id")
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Integration tests should use Embedded Kafka or Testcontainers to verify headers sent through the broker retain exact names, occurrence counts, and byte values. In particular, if using `Message<?>` with `DefaultKafkaHeaderMapper`, inspect actual records to confirm header encoding matches the contract of non-Spring services.

## 13. Shared header convention checklist

- [ ] Maintain centralized contract documentation for each header's name, meaning, and format.
- [ ] Use lowercase ASCII and `kebab-case` for custom header names.
- [ ] Define required, optional, and cardinality rules for headers.
- [ ] Encode/decode strings using UTF-8.
- [ ] Ensure `event-id`, `event-type`, `content-type`, and `schema-version` have consistent semantics.
- [ ] Distinguish `event-id`, `correlation-id`, `causation-id`, and `traceparent`.
- [ ] Do not use headers in place of the Kafka key or essential business data.
- [ ] Use a tracing propagator to inject/extract trace context.
- [ ] Have a backward-compatible process for adding, deprecating, and removing headers.
- [ ] Never put secrets or large payloads into headers.
- [ ] Forward headers strictly via an allowlist.
- [ ] Test actual headers through the broker and across producer/consumer versions.

Shared header conventions help services interpret metadata consistently, from event identification to tracing and versioning. Treat headers as part of the inter-service contract: keep naming stable, encode explicitly, define cardinality, and evolve along a compatible rollout path so Spring Kafka systems stay easy to integrate and operate.
