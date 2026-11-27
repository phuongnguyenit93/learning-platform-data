# Limiting Header Size and Avoiding Sensitive Data

In Spring Cloud Stream, a message typically consists of a payload and headers. The payload carries business data; headers carry metadata that assists routing, tracing, interpretation, or message handling, such as event ID, correlation ID, schema version, and tracing context. Because headers travel alongside the message through the binder and broker, they also consume space, are subject to transport limits, and can show up in logs, dead-letter queues, or operational tools.

A large header can inflate message size, cause publish/consume failures, or degrade throughput. Headers containing passwords, access tokens, cookies, personally identifiable information, or payment data also introduce leakage risks. Good design means sending only small, well-defined metadata, restricting the allowed header list, and checking sizes before passing a message to a binding.

## 1. What Are Headers Used For?

Spring Messaging represents a message using `Message<T>`, where `T` is the payload type and `MessageHeaders` is the metadata collection. Example:

```java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001", 250_000))
    .setHeader("eventId", "evt-7f23")
    .setHeader("correlationId", "corr-91ab")
    .setHeader("schemaVersion", "1")
    .build();
```

The payload is `OrderCreated`; the values `eventId`, `correlationId`, and `schemaVersion` are metadata. They help consumers deduplicate, link messages within a processing flow, and select how to interpret the schema. If a consumer only needs order data, it can accept the payload directly; when metadata is needed, the function can accept `Message<OrderCreated>`.

A header should answer a specific technical question:

| Metadata | Purpose | Note |
|---|---|---|
| `eventId` | Uniquely identifies an event | Used as an idempotency key; must not contain personal data |
| `correlationId` | Links steps within a request or workflow | Use unguessable or opaque values if potentially linked to a user |
| `schemaVersion` | Identifies payload structure version | Agree on conventions between producer and consumer |
| `traceparent` | Propagates W3C distributed tracing context | Only pass values conforming to the system's tracing format and policy |
| `contentType` | Describes content format | Usually managed by framework/binder; avoid setting conflicting values manually |

Never use headers to duplicate the entire payload, embed a large object as JSON, or pass lengthy business state. If consumers need substantial data for processing, put it in a schema-defined payload or store it in an appropriate system and pass a stable reference.

## 2. Headers Also Have Size Limits

There is no single header size limit that applies to every Spring Cloud Stream application. Actual limits depend on multiple layers:

1. **Application:** size policies defined by the development team, along with allowed header types and counts.
2. **Spring Messaging and binder:** how mappers translate `MessageHeaders` into broker metadata, which headers are preserved, type-converted, or dropped.
3. **Client and protocol:** request, frame, record, or metadata limits that the client can construct and send.
4. **Broker and destination:** message size limits, topic/queue configuration, storage policies, and replication.
5. **Consumers and intermediaries:** limits when reading, forwarding, logging, tracing, or routing messages to a DLQ.

Header size is usually counted together with message overhead. Header names, values, encoding formats, framework-added metadata, and protocol framing can all increase actual size. Consequently, summing the bytes of header strings on the application side is only an estimate, not an exact measurement of wire message size.

### Differences Across Brokers

| Broker | How headers/metadata are carried | Limits to verify |
|---|---|---|
| Kafka | Record headers with byte-valued names and values; headers live inside records sent in requests/batches | Producer request size, broker/topic record/message size limits, and consumer fetch limits |
| RabbitMQ | Message properties containing headers as an AMQP field table | Supported field table data types, frame size, message limits, and broker/client settings |
| Pulsar | Message properties are key/value pairs stored in message metadata | Client/broker message size limits and metadata serialization overhead |

Kafka, RabbitMQ, and Pulsar do not encode headers the same way. The same `MessageHeaders` map can be mapped differently across binders. A header with a custom Java type or an overly long value might work in one binder yet be converted, ignored, or rejected in another. When supporting multiple brokers, pick a small common denominator of headers and test each binder.

Do not apply a single default broker number across every environment. Check the configuration of the deployed clients and brokers, and account for intermediate components. For example, check request/record and fetch limits for Kafka; AMQP frame and message properties for RabbitMQ; and message plus metadata limits for Pulsar. Increasing broker limits merely to accommodate bloated headers usually hides design flaws and raises memory, network, and storage costs.

## 3. Setting a Header Budget at the Application Layer

Even when brokers allow large messages, the application should enforce a smaller budget than infrastructure limits. A budget catches issues early, keeps metadata consistent across brokers, and prevents a service from accidentally stuffing large data into headers.

An illustrative policy might specify:

- Allow only an approved list of headers.
- Limit the number of custom headers, e.g., at most 8 fields.
- Limit total bytes of names and values, e.g., 4 KiB for custom metadata.
- Cap each individual value, e.g., 1 KiB.
- Allow only simple types with explicit conversion rules, such as `String`, numbers, or booleans.
- Reject unexpectedly empty values, oversized values, and headers not on the allowlist.

The numbers above are an example application budget, not default limits of Spring Cloud Stream or any broker. Choose thresholds lower than the smallest limit among the brokers and intermediaries your system actually uses, leaving headroom for framework- and protocol-added metadata.

Measure string size in UTF-8 bytes rather than Java character counts. A string with accented characters or emojis can occupy more bytes than visible characters:

```java
int byteLength = value.getBytes(StandardCharsets.UTF_8).length;
```

Do not use `String.length()` to determine the data size that will travel over the broker. For `byte[]` values, check the array length directly; for complex types, you must know the exact serializer and encoding format before estimating.

## 4. Allowlists and Pre-Send Header Validation

An allowlist explicitly defines which metadata may cross service boundaries. The following example accepts only four string headers and caps total custom metadata size at 4 KiB:

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Set;

public final class SafeHeaders {
    private static final Set<String> ALLOWED = Set.of(
        "eventId",
        "correlationId",
        "schemaVersion",
        "traceparent"
    );

    private static final int MAX_HEADER_COUNT = 8;
    private static final int MAX_HEADER_BYTES = 4 * 1024;
    private static final int MAX_VALUE_BYTES = 1024;

    private SafeHeaders() {}

    public static Map<String, String> validate(Map<String, String> input) {
        if (input.size() > MAX_HEADER_COUNT) {
            throw new IllegalArgumentException("Too many message headers");
        }

        int totalBytes = 0;
        for (Map.Entry<String, String> entry : input.entrySet()) {
            String name = entry.getKey();
            String value = entry.getValue();

            if (!ALLOWED.contains(name)) {
                throw new IllegalArgumentException("Header is not allowed: " + name);
            }
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Header value is required: " + name);
            }

            int nameBytes = name.getBytes(StandardCharsets.UTF_8).length;
            int valueBytes = value.getBytes(StandardCharsets.UTF_8).length;
            if (valueBytes > MAX_VALUE_BYTES) {
                throw new IllegalArgumentException("Header value is too large: " + name);
            }
            totalBytes += nameBytes + valueBytes;
        }

        if (totalBytes > MAX_HEADER_BYTES) {
            throw new IllegalArgumentException("Message headers exceed the application budget");
        }
        return Map.copyOf(input);
    }
}
```

When creating a message, copy only headers that passed validation:

```java
Map<String, String> metadata = Map.of(
    "eventId", event.eventId(),
    "correlationId", correlationId,
    "schemaVersion", "1"
);

Map<String, String> safeMetadata = SafeHeaders.validate(metadata);

Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .copyHeaders(safeMetadata)
    .build();
```

This example validates custom headers at the producer boundary. In real applications, align the allowlist across services and inspect headers added automatically by frameworks, tracing agents, or binders. If business needs require an additional header, update the schema/allowlist in a controlled manner rather than permitting arbitrary headers.

## 5. Transmit Only Needed Metadata

A header should be small, stable, and clearly purposed. Appropriate values are typically technical IDs, schema versions, event types, or tracing context. Avoid the following contents:

| Do not put in headers | Why it is risky | Better alternative |
|---|---|---|
| Passwords, API keys, access tokens, refresh tokens | Can be copied into brokers, DLQs, logs, or tracing systems | Use a secret manager and service identities; authenticate at the transport channel |
| Session cookies or full HTTP Authorization headers | Can grant unintended privileges and be replayed | Do not forward request credentials; establish proper service-to-service identity/authorization |
| Full names, emails, phone numbers, addresses, national IDs | Metadata may be observed by many components and retained long-term | Use an internal ID or opaque reference if consumers need to look up details |
| Card numbers, payment data, or financial details | Expands the scope of sensitive data requiring protection and access control | Pass a securely designed payment token or reference |
| Entire user or order objects | Bloats headers, hurts compatibility, and duplicates the payload | Place business data inside a schema-defined payload |
| Stack traces, exception messages, or debug dumps | Can expose file paths, class names, SQL, request data, or secrets | Send a short error code and correlation ID; store details in a controlled logging system |

Never treat headers as a private channel simply because they are not visible inside the payload. Broker operators, authorized consumers, admin tools, dead-letter queues, connectors, logs, and tracing systems can all inspect metadata. TLS protects data in transit, but it does not eliminate risk once data is persisted on the broker or viewed by authorized personnel.

If a consumer needs sensitive information for processing, evaluate whether it can look it up from an access-controlled system using an ID. If transmitting sensitive data is unavoidable, place it in the payload under an appropriate schema and protection policy, restrict read permissions, encrypt as required, and configure retention. Never use headers as a covert channel in place of proper security controls.

## 6. Headers Are Not Authentication Proof

Producers can create or alter many headers. Therefore, a consumer must never trust headers like `userRole`, `isAdmin`, `authenticatedUser`, or `tenantId` solely because they arrived from a broker. A compromised producer or a client with publish permissions can forge that metadata.

If a header influences authorization decisions, the consumer must verify the origin and integrity of that information using appropriate mechanisms. Typically, rely on authenticated service identities, verified signatures/claims, or lookups from a trusted source. A header may carry a correlation ID or identifier reference, but it does not by itself prove the sender is authorized to perform an action.

For tenant context, transmit a tenant ID only when genuinely needed and ensure consumers verify that the producer is permitted to emit events for that tenant. Never take a tenant value from an unverified header to access another tenant's data.

## 7. Filtering Headers Across the Binder

Spring Cloud Stream sends application messages through a binder. The binder and header mapper determine which headers map to native broker metadata, which are type-converted, and which are dropped. Some transports have native header mechanisms; some configurations may package headers in a custom format. Never assume every custom header is preserved intact when switching binders.

Configuration guidelines:

- Prefer an allowlist at the application boundary before calling `StreamBridge` or returning a message from a function.
- Use the binder's header mapping/pattern capabilities to transfer only required headers, following the documentation for your exact binder version.
- Do not enable a pass-all-headers mode merely to retain a single metadata field.
- Avoid forwarding internal HTTP, framework, or security headers if consumers do not need them.
- Inspect framework-generated headers such as ID and timestamp; retain or forward them only when meaningful to the business flow.
- When migrating from Kafka to RabbitMQ or Pulsar, re-verify header names, data types, size limits, and filtering rules.

For example, a function can preserve the correlation ID and replace the event type:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        OrderAccepted accepted = new OrderAccepted(order.orderId(), order.total());

        return MessageBuilder.withPayload(accepted)
            .setHeader("eventId", UUID.randomUUID().toString())
            .setHeader("correlationId", input.getHeaders().get("correlationId"))
            .setHeader("schemaVersion", "1")
            .setHeader("eventType", "OrderAccepted")
            .build();
    };
}
```

This example illustrates constructing new metadata using an allowlist. Before using it in production, validate the incoming correlation ID value, handle missing/null cases, and confirm that the binder's header mapper allows these exact header names. Avoid defaulting to a full `copyHeaders` if inputs might contain untrusted headers or data that should not be broadcast.

## 8. Avoiding Data Leaks Through Logs, Retries, and DLQs

Headers may be recorded alongside messages in application logs, broker logs, or observability tools. Logging an entire `Message`, `MessageHeaders`, or request object can inadvertently write tokens and personal data. Log an approved set of fields instead, such as event ID, event type, binding name, and correlation ID after privacy review.

Controlled logging example:

```java
log.info("Received event: eventId={}, binding={}, type={}",
    eventId, bindingName, eventType);
```

Avoid:

```java
log.info("Received message: {}", message);
```

When a message is retried or routed to a DLQ, headers are typically retained or copied according to binder behavior. Consequently, sensitive data in headers can persist longer than expected and reappear during replay workflows. Before enabling a DLQ or republishing, check how headers are retained, augmented, and logged. Topic/queue and DLQ retention policies are also part of your data governance policy.

Do not place stack traces or full exception messages into headers for debugging convenience. Use short error codes, event IDs, and correlation IDs to locate details in a logging system with access controls, bounded retention, and data masking.

## 9. Testing Header Limits and Policies

Tests should verify both valid inputs and rejected cases:

- Send a message with a minimal header set and verify the consumer receives the required metadata.
- Send headers with multi-byte UTF-8 values, such as Vietnamese text or emojis, to test size calculation.
- Send an individual value exceeding the per-header cap or total headers exceeding the budget; verify the producer rejects it before publishing.
- Send a header name not on the allowlist and confirm it is not forwarded.
- Test values with unsupported types and verify the mapper handles them per policy.
- Inspect headers after messages pass through each real binder; confirm names, types, values, and handling order are not misinterpreted.
- Inspect logs, retries, and DLQs to verify no tokens, cookies, or personal data appear unexpectedly.
- Test with payload sizes near the broker limit, since headers and overhead also contribute to total message size.

The test binder is useful for verifying message logic within the application, but it does not replace testing against real Kafka, RabbitMQ, or Pulsar instances when verifying protocol limits, header mapping, record/frame/metadata sizes, and DLQ behavior. Maintain dedicated integration tests for each deployed binder.

## 10. Safe Header Design Checklist

- [ ] Every header has a specific purpose and is genuinely needed by consumers.
- [ ] Headers contain only small metadata; business data lives in a schema-defined payload.
- [ ] An allowlist defines accepted header names and value types.
- [ ] Header count, per-value size, and total UTF-8 byte count are capped at the application layer.
- [ ] The application budget sits below the actual limits of brokers, clients, and intermediaries.
- [ ] No passwords, tokens, cookies, personal data, or payment details are transmitted in headers.
- [ ] Headers are never used as proof of authentication or authorization without verifying origin.
- [ ] Binder header mappers forward only required fields.
- [ ] Logs, retries, DLQs, and traces do not expose sensitive metadata.
- [ ] Size limits and header mapping have been tested against every broker in use.

Small, controlled headers keep messages portable across binders, reduce overhead, and improve safety as messages pass through brokers, logs, retries, and DLQs. Treat all published metadata as observable by many components across the system, and transmit only what is strictly necessary to process the event.
