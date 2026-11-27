# Headers Lost, Unintentionally Copied, or Failed to Add

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish payload, Spring `Message`, `MessageHeaders`, and protocol-native headers.
2. Explain why custom headers disappear when building a new `Message`, changing the payload, or passing through function composition.
3. Use `MessageBuilder.fromMessage`, `copyHeaders`, `copyHeadersIfAbsent`, `setHeader`, `setHeaderIfAbsent`, and `removeHeader` appropriately.
4. Recognize system headers such as `id`, `timestamp`, `contentType`, `replyChannel`, and `errorChannel`, and the limits on modifying or forwarding them.
5. Diagnose headers not mapped across HTTP, Kafka, RabbitMQ, or serverless adapters; distinguish Spring headers from native transport headers.
6. Enrich headers in a controlled manner via dedicated functions, avoiding copying credentials, internal headers, or unsuitable metadata across trust boundaries.
7. Design tests for three cases: headers preserved, headers unintentionally overwritten, and header enrichment failing.
8. Use logs and traces to pinpoint the exact step that drops a header without logging full sensitive values.

## 1. Why Do Headers Matter in Spring Cloud Function?

Spring Cloud Function lets you package business logic as `Supplier`, `Function`, and `Consumer`, look them up via `FunctionCatalog`, compose them, and convert messages. The same function can be invoked over HTTP, events, or serverless runtimes.

A Spring Messaging `Message<T>` has two parts:

- **Payload:** business data, such as an `Order`, `String`, JSON, or an event.
- **Headers:** accompanying metadata, such as `businessCorrelationId`, `contentType`, `replyChannel`, `id`, `timestamp`, or broker-provided headers.

Example message:

~~~text
Message<Order>
  payload:
    orderId = 1024
    amount = 250000
  headers:
    businessCorrelationId = flow-72
    contentType = application/json
    id = UUID managed by Spring
    timestamp = message creation time
~~~

The payload can remain intact while headers vanish. That commonly breaks metadata-dependent features:

- No correlation ID remains to tie producer and consumer logs together.
- The router never receives the target-selection instruction.
- Converters do not know which content type represents the payload.
- Reply channels or error channels stop matching internal flows.
- Consumers fail to read custom metadata sent by producers.

Headers can also be **unintentionally copied**. For example, a function copies all HTTP request headers into a Kafka message, accidentally leaking `Authorization`, cookies, or internal headers. Consequently, header diagnostics must answer two questions: *which headers must be kept?* and *which headers must not cross the boundary?*

~~~mermaid
flowchart LR
    A["HTTP / Broker input"] --> B["Spring Message"]
    B --> C["Function A"]
    C --> D["New Message"]
    D --> E["Function B / Composition"]
    E --> F["Output / Broker"]
    H["Custom headers"] -. "need intentional mapping/copy" .-> C
    H -. "verify after each boundary" .-> D
    H -. "allowlist before publish" .-> F
~~~

## 2. Distinguish Four Metadata Layers

Not everything called a "header" is the same data structure.

| Layer | Examples | Managed by |
| --- | --- | --- |
| Spring `MessageHeaders` | `businessCorrelationId`, `contentType`, `id` | Spring Messaging and application |
| HTTP headers | `X-Correlation-Id`, `Content-Type`, `Authorization` | HTTP client/server and adapter |
| Broker/native headers | Kafka record headers, RabbitMQ properties/headers | Broker, binder, and header mapper |
| Function routing metadata | Definition/routing expression per config and version | Spring Cloud Function/router |

An HTTP header reaches `MessageHeaders` only if the adapter or application code maps it into the message. A Spring custom header reaches Kafka/RabbitMQ only if the binder/header mapper supports it and configuration allows forwarding. Two layers sharing a header name string does not mean the framework automatically copies values between them.

### Header Names and Data Types

- HTTP header names are case-insensitive under HTTP rules; Spring `MessageHeaders` is a map with exact key names. When mapping manually, pick a consistent convention such as `businessCorrelationId`.
- Broker headers may support only specific types or represent values as byte arrays; arbitrary Java objects may fail serialization.
- Header values can convert into `String`, `byte[]`, or another type across transports. Consumers must match the data-type contract.
- `contentType` affects message conversion; a wrong or missing content type can cause deserialization failures even when the payload arrives intact.

## 3. MessageHeaders: Immutability and System Headers

`MessageHeaders` is an immutable map on its public interface. You cannot grab the map from `message.getHeaders()` and mutate it directly:

~~~java
message.getHeaders().put("businessCorrelationId", "flow-72");
~~~

That is not a valid way to update headers; the headers map is guarded against direct mutation. Build a new message with `MessageBuilder` or use an appropriate accessor API.

### Headers to Recognize

| Header | Role | Notes |
| --- | --- | --- |
| `id` | Spring `Message` identifier | Managed by the framework; do not assign arbitrarily |
| `timestamp` | Message creation timestamp | System header; do not treat as a business timestamp |
| `contentType` | Format/content hint for converters | Must stay consistent with the actual payload |
| `replyChannel` | Reply channel in certain Spring Messaging/Integration flows | Often an internal object, not metadata to serialize over a broker |
| `errorChannel` | Internal error channel | Do not copy onto transports as a custom string header |
| `businessCorrelationId` | Application-defined workflow correlation | Needs a clear generation, validation, and propagation contract |
| `sourceMessageId` | Application-defined source message reference | Distinct from the current message's `MessageHeaders.ID` |

`id` and `timestamp` are Spring-managed headers and should not be overwritten via `setHeader`. When creating new messages, let the framework handle them. Whether a builder API preserves or regenerates system values can depend on how the message was created and the framework version; **never use `id`/`timestamp` as proof that all custom headers survived**.

## 4. Creating a New Message Can Drop Headers

This is the most common cause:

~~~java
Message<String> input = ...;

Message<String> output = MessageBuilder
        .withPayload(input.getPayload().toUpperCase(java.util.Locale.ROOT))
        .build();
~~~

`MessageBuilder.withPayload(...)` starts a brand-new message. Unless you copy or set headers, custom headers from `input` are absent in the builder.

Example input:

~~~text
payload = "hello"
businessCorrelationId = flow-72
tenantTier = standard
~~~

After the code above, the output has payload `HELLO`, yet lacks `businessCorrelationId` and `tenantTier`.

### Preserving Headers When Replacing the Payload

~~~java
import java.util.Locale;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> transform(Message<String> input) {
    String output = input.getPayload()
            .trim()
            .toUpperCase(Locale.ROOT);

    return MessageBuilder.withPayload(output)
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

`copyHeaders(...)` copies copyable headers into the builder per Spring Messaging rules. Read-only system headers like `id` and `timestamp` are controlled by Spring; do not rely on copying to manipulate them directly.

### Keeping Only a Selected Set of Headers

In many applications, copying every header is undesirable. Define an allowlist:

~~~java
import java.util.Map;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> transformWithAllowedHeaders(Message<String> input) {
    Set<String> allowed = Set.of(
            "businessCorrelationId",
            "tenantTier",
            "contentType");

    Map<String, Object> selected = input.getHeaders().entrySet().stream()
            .filter(entry -> allowed.contains(entry.getKey()))
            .collect(Collectors.toMap(
                    Map.Entry::getKey,
                    Map.Entry::getValue));

    String output = input.getPayload().trim()
            .toUpperCase(Locale.ROOT);

    return MessageBuilder.withPayload(output)
            .copyHeaders(selected)
            .build();
}
~~~

This example illustrates **allowlist-based copying**. Decide explicitly whether the old `contentType` should still be forwarded when the payload changes type. If the output payload uses a different type or format, set a content type matching the output.

## 5. MessageBuilder: Pick the Right Operation

Spring provides builder operations with distinct semantics.

| API | Meaning | When to use |
| --- | --- | --- |
| `withPayload(payload)` | Start a new message from payload | Creating a new output |
| `fromMessage(message)` | Create a builder from an existing message | Keep payload/headers while modifying specific headers |
| `setHeader(name, value)` | Set or replace a header value | When the new value should win |
| `setHeaderIfAbsent(name, value)` | Set only if the header is absent | Keep existing source value when already present |
| `copyHeaders(map)` | Copy headers into builder; copied values can replace existing ones per API rules | When the source map should overwrite colliding keys |
| `copyHeadersIfAbsent(map)` | Copy only keys not yet set on the builder | Keep values already set on the builder |
| `removeHeader(name)` | Remove a single header | Strip metadata that no longer applies |
| `removeHeaders(patterns...)` | Remove headers matching patterns | Clean up a group of headers by naming pattern |
| `build()` | Construct the `Message` from configured payload and headers | Finish transformation |

### `fromMessage`: Change a Header While Keeping Payload

~~~java
Message<String> enrich(Message<String> input) {
    return MessageBuilder.fromMessage(input)
            .setHeader("processingStage", "validated")
            .build();
}
~~~

This is the clearest option when the payload does not change and only metadata needs adding or updating.

### `copyHeaders` Can Overwrite Values

~~~java
import java.util.Map;

Message<String> output = MessageBuilder.withPayload("HELLO")
        .setHeader("businessCorrelationId", "flow-output")
        .copyHeaders(Map.of("businessCorrelationId", "flow-input"))
        .build();
~~~

Calling `copyHeaders` after setting a same-named header allows the map's value to overwrite the existing value. If you want `flow-output` to win, use `copyHeadersIfAbsent` or call `setHeader` **after** copying.

### `copyHeadersIfAbsent` Preserves Existing Values

~~~java
import java.util.Map;

Message<String> output = MessageBuilder.withPayload("HELLO")
        .setHeader("businessCorrelationId", "flow-output")
        .copyHeadersIfAbsent(Map.of(
                "businessCorrelationId", "flow-input",
                "sourceSystem", "order-api"))
        .build();
~~~

Expected result:

~~~text
businessCorrelationId = flow-output
sourceSystem = order-api
~~~

### `setHeaderIfAbsent` Is Not Map Merging

~~~java
Message<String> output = MessageBuilder.fromMessage(input)
        .setHeaderIfAbsent("businessCorrelationId", "generated-flow")
        .build();
~~~

If `input` already has `businessCorrelationId`, the old value stays. Otherwise, the builder sets the default. Check how empty/null values are handled by your application's contract; if you need to replace blank or invalid values, validate first and call `setHeader`.

### Nulls and Removing Headers

In the builder API, `setHeader(name, null)` carries removal semantics for that header. For clearer, less error-prone code, use `removeHeader(name)`:

~~~java
Message<String> output = MessageBuilder.fromMessage(input)
        .removeHeader("temporaryRoutingHint")
        .build();
~~~

Never use the literal string `"null"` to represent an absent header; that is a real value and can break consumers.

## 6. Adding Headers with a Dedicated Function

An enrichment function can attach metadata without coupling business logic to HTTP or brokers:

~~~java
import java.util.UUID;
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Function<Message<String>, Message<String>> addProcessingMetadata =
        input -> MessageBuilder.fromMessage(input)
                .setHeader("processingStage", "normalized")
                .setHeaderIfAbsent(
                        "businessCorrelationId",
                        UUID.randomUUID().toString())
                .build();
~~~

This function generates a correlation ID only when the header is missing. In production, decide clearly who is authorized to issue IDs and whether external IDs are trusted; validate values before accepting them.

### Replacing Payload and Enriching in the Same Function

~~~java
Function<Message<String>, Message<String>> normalizeAndEnrich =
        input -> {
            String output = input.getPayload().trim()
                    .toUpperCase(Locale.ROOT);

            return MessageBuilder.withPayload(output)
                    .copyHeadersIfAbsent(input.getHeaders())
                    .setHeader("processingStage", "normalized")
                    .build();
        };
~~~

This function:

1. Reads the incoming payload.
2. Produces the new payload.
3. Copies source headers not already set on the builder.
4. Sets `processingStage=normalized` so the current stage wins.

If an old `contentType` described the input payload while the output changed format, update or drop that header so adapters pick the right converter. Mechanically preserving every header is not always appropriate.

## 7. Headers in Function Composition

Spring Cloud Function supports composition, for example:

~~~properties
spring.cloud.function.definition=normalize|addProcessingMetadata|saveResult
~~~

Each function receives the previous step's output. For functions operating on `Message`, define clearly what each stage accepts and returns:

- `Message<T>` when it needs to read or write metadata.
- `T` when it only transforms the payload and needs no headers.

### A Function Returning a Raw Payload Can Drop Metadata at the Contract Level

~~~java
Function<Message<String>, String> extractPayload =
        message -> message.getPayload().trim();
~~~

This function deliberately returns only `String`. Once the next step accepts a plain payload, it cannot read custom headers from the original input `Message` unless the adapter/framework retains them out-of-band.

If downstream steps need headers, there are two options:

1. Have functions along that boundary accept and return `Message`.
2. Pass the needed metadata explicitly in a domain data type rather than relying on implicit headers.

### Explicit Message Composition

~~~java
Function<Message<String>, Message<String>> normalize =
        message -> MessageBuilder.withPayload(
                        message.getPayload().trim()
                                .toUpperCase(Locale.ROOT))
                .copyHeaders(message.getHeaders())
                .setHeader("processingStage", "normalized")
                .build();

Function<Message<String>, Message<String>> markReady =
        message -> MessageBuilder.fromMessage(message)
                .setHeader("processingStage", "ready")
                .build();

Function<Message<String>, Message<String>> chain =
        normalize.andThen(markReady);
~~~

This is pure Java composition, making input/output types explicit. For catalog compositions, adapters, and Spring Cloud Function invocation wrappers, verify function signatures and message-wrapping rules for your version. **Do not assume every custom header automatically survives every kind of composition**, especially when a stage returns a plain payload or triggers message conversion.

## 8. Distinguish Business Headers, Routing Headers, and Internal Headers

Do not copy all headers blindly because different headers serve different purposes.

| Category | Examples | Policy |
| --- | --- | --- |
| Business | `businessCorrelationId`, `eventType`, `tenantTier` | Forward per allowlist/contract |
| Conversion | `contentType`, schema/version metadata | Keep or update to match payload |
| Routing | Function definition/routing expression per config | Forward only where routing is needed; enforce allowlists |
| Observability | Trace context, baggage, correlation metadata | Let tracer/adapter propagators manage; do not copy blindly |
| Spring internal | `replyChannel`, `errorChannel` | Do not serialize/publish over brokers by default |
| Security | `Authorization`, cookies, credentials, session | Never copy onto messages/brokers/logs unless backed by explicit security design |
| Broker native | Partition/offset, delivery metadata | Read at adapter; do not assume custom Spring headers round-trip back |

### Why Is "Copy All" Dangerous?

Suppose an HTTP request contains:

~~~text
Authorization: Bearer <token>
Cookie: SESSION=<session>
X-Correlation-Id: flow-72
X-Tenant-Tier: standard
~~~

If the adapter places everything into `MessageHeaders` and a function calls `copyHeaders(...)` before publishing to Kafka, tokens and sessions leak onto the broker and outlive the original request.

Prefer forwarding:

~~~text
businessCorrelationId
tenantTier
contentType (if still accurate for output)
~~~

Do not forward:

~~~text
Authorization
Cookie
session
replyChannel
errorChannel
~~~

Trace-context propagation should follow your tracer and binder instrumentation rather than copying raw `traceparent` strings ad hoc.

## 9. Headers Lost When Crossing HTTP

HTTP headers and Spring `MessageHeaders` are distinct structures. An adapter may:

- Copy selected HTTP headers into the Spring message.
- Normalize or rename headers.
- Forward only allowlisted headers.
- Drop unsupported or unsafe headers.
- Store metadata in a separate structure outside `MessageHeaders`.

When mapping must be guaranteed, map explicitly in an application-controlled controller, filter, or adapter:

~~~java
import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> toMessage(String body, HttpHeaders httpHeaders) {
    String correlationId =
            httpHeaders.getFirst("X-Correlation-Id");

    MessageBuilder<String> builder = MessageBuilder.withPayload(body);
    if (correlationId != null
            && Pattern.matches("[A-Za-z0-9._-]{1,64}", correlationId)) {
        builder.setHeader("businessCorrelationId", correlationId);
    }

    builder.setHeader("source", "http");
    return builder.build();
}
~~~

This example copies only a chosen header after validating length and allowed characters. Depending on your API contract, invalid headers may return 400 rather than being ignored; never log raw invalid values verbatim.

### Diagnosing HTTP Mapping

1. Verify the actual incoming request carries the header.
2. Check the header name after HTTP framework parsing.
3. Verify the controller/filter maps the header into `MessageBuilder`.
4. Inspect the `Message` right before the function.
5. Inspect the output `Message` right after the function.
6. If output is right yet downstream loses it, inspect the response adapter / HTTP client.

Do not look solely at the browser/`curl` request and assume the function received the header.

## 10. Headers Lost When Crossing Spring Cloud Stream / Brokers

Spring Cloud Stream provides the `Message` abstraction for bindings, yet forwarding custom headers to the broker depends on the binder, header mapper, serialization, and configuration.

### Common Causes

- The binder or transport does not support the expected header mode.
- The header mapper permits only certain keys or types.
- A custom header value cannot be serialized or has an unsupported type.
- Headers were placed in native headers while the consumer reads Spring headers (or vice versa).
- Producer and consumer disagree on header names or data types.
- A message converter transforms payload/`contentType` without mapping custom metadata as expected.
- Headers exceed broker or adapter size limits.

### Kafka

Kafka records carry native headers as key/value byte arrays. The Spring Cloud Stream Kafka binder maps Spring message headers to Kafka headers according to version-specific config and mappers. A `String` header at the producer may appear as bytes inside the record; consumers must decode it accordingly.

Do not assume arbitrary Java objects serialize automatically. Prefer simple, well-defined types such as `String`, numbers, or byte arrays and verify the active mapper. Broker metadata like topic, partition, and offset are transport fields; do not treat them as custom business headers.

### RabbitMQ

RabbitMQ has AMQP properties and headers. Header types and mappings depend on the client and binder. Unsupported types, oversized values, or special metadata can fail conversion or be dropped. Inspect both the message on the broker and the message received by the consumer, not only the pre-publish message object.

### Header Modes and Binder Configuration

Binders provide their own header mode/mapper settings; no single config applies uniformly across Kafka, RabbitMQ, SQS, and all binders. Read the docs for your exact binder and verify:

- Is header mapping mode enabled?
- Is the custom header included in mapped headers?
- Is native encoding/decoding active?
- Are there type or size limits?
- Do producer and consumer share the same key/type conventions?

If a binder is configured in a mode that omits headers, payloads arrive intact while custom headers vanish. That is a mapping/configuration issue, not a `MessageBuilder` bug.

## 11. Routing Headers and Function Control Metadata

Function routing can rely on definitions, routing expressions, callbacks, or adapter-specific metadata. Routing control headers must be kept separate from business headers:

- Accept only routes on an allowlist.
- Verify the adapter/binder forwards the header to the router properly.
- Do not forward routing hints to another topic if the target consumer should not act on them.
- Do not use client-supplied route names as unbounded metric labels or log fields.
- Once a function has been selected, strip temporary routing hints if downstream no longer needs them.

Example removing a temporary routing hint after target selection:

~~~java
Message<String> routed = MessageBuilder.fromMessage(input)
        .removeHeader("temporaryRoutingHint")
        .setHeader("processingStage", "routed")
        .build();
~~~

`temporaryRoutingHint` here is an application-defined custom header. Do not strip Spring system headers or routing headers still needed by the framework before routing completes.

### Routing Failure Does Not Always Mean a Lost Header

When the router fails to select a function, distinguish:

1. The header is absent from the message.
2. The header is present, yet the key name disagrees with the contract.
3. The header is present, yet its value is empty, wrong type, or invalid.
4. The header is valid, yet the function definition is unregistered in the catalog.
5. The routing expression or callback threw an exception.

Log key presence and a bounded reason code for diagnostics; never log entire header maps or client-supplied expressions verbatim.

## 12. Header Enrichment Failing Due to Types, Nulls, or Converters

Not every enrichment bug originates in the builder. Several occur during conversion or serialization:

| Symptom | Cause |
| --- | --- |
| Header set, then lost after publish | Header mapper dropped the key or type |
| Header becomes a String instead of an object | Transport/mapper encoded value as text |
| Header fails deserialization | Consumer expects a different type than producer sent |
| Header absent when value is `null` | Builder or mapper omits `null` values |
| Header present, function cannot read it | Different key name, casing/convention mismatch, or wrong accessor layer |
| Payload conversion fails after enrichment | `contentType` mismatches the payload |
| Header fails to cross the broker | Value too large or unsupported type |

### Use Simple Header Types

For cross-service metadata, prefer:

- Short, well-formatted Strings for correlation IDs or event types.
- Booleans or integers when supported by the transport contract.
- Byte arrays when versioned binary formats are needed.

Avoid putting arbitrary objects, Spring channel objects, `HttpServletRequest`, exceptions, or domain aggregates directly into headers. Headers are small metadata, not a second payload.

### Verify Types Before and After Boundaries

At the producer:

~~~java
Object value = message.getHeaders().get("businessCorrelationId");
log.debug("correlation header present={}, type={}",
        value != null,
        value == null ? "absent" : value.getClass().getSimpleName());
~~~

Run the same check at the consumer. Log only the type name and present/absent flag; never log values if a header could hold sensitive data.

If the producer sends `String` yet the consumer receives `byte[]`, the mapper converted the type. Decode per contract instead of casting directly:

~~~java
String correlationId;
if (value instanceof String text) {
    correlationId = text;
}
else if (value instanceof byte[] bytes) {
    correlationId = new String(
            bytes, java.nio.charset.StandardCharsets.UTF_8);
}
else {
    throw new IllegalArgumentException(
            "Unsupported correlation header type");
}
~~~

This example uses pattern matching for `instanceof`, requiring Java 16+; on older Java versions, use `instanceof` with an explicit cast.

## 13. Inspecting Headers at Every Boundary

To pinpoint where a header disappears, inspect messages at these checkpoints:

~~~text
1. HTTP/broker ingress
2. Message after adapter/converter
3. Input to function A
4. Output from function A
5. Input to function B
6. Message before publish
7. Native record/header on the broker
8. Message after consumer adapter
~~~

Build a comparison table:

| Boundary | `businessCorrelationId` | `contentType` | `source` |
| --- | --- | --- | --- |
| HTTP ingress | Present | `text/plain` | Absent |
| Input message | Present | `text/plain` | `http` |
| After normalize | Present | `text/plain` | `http` |
| Before Kafka publish | Present | `text/plain` | `http` |
| After Kafka consume | Present/absent depending on mapper | `text/plain`/bytes | `http` |

If a header first disappears at boundary 6→7, inspect the binder/header mapper. If it already vanished at 3→4, inspect function code. Do not rewrite the whole pipeline before knowing which boundary altered the data.

### Log Header Names, Not All Values

You can log:

~~~java
log.debug("message headers present={}",
        message.getHeaders().keySet());
~~~

`keySet()` can still reveal internal header names; use it in controlled debug environments. Avoid:

~~~java
log.debug("headers={}", message.getHeaders());
~~~

because values may hold tokens, cookies, PII, reply/error channels, or business data. To verify a single custom header, log its presence or an already-validated ID:

~~~java
boolean hasCorrelationId = message.getHeaders()
        .containsKey("businessCorrelationId");
log.debug("business correlation header present={}", hasCorrelationId);
~~~

## 14. Testing Preservation, Overwriting, and Enrichment of Headers

### 14.1. Headers Preserved When Changing Payload

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderPropagationTest {

    @Test
    void keepsBusinessHeadersWhenPayloadChanges() {
        Message<String> input = MessageBuilder.withPayload(" hello ")
                .setHeader("businessCorrelationId", "flow-72")
                .setHeader("source", "http")
                .build();

        String transformed = input.getPayload()
                .trim()
                .toUpperCase(Locale.ROOT);

        Message<String> output = MessageBuilder
                .withPayload(transformed)
                .copyHeaders(input.getHeaders())
                .build();

        assertEquals("HELLO", output.getPayload());
        assertEquals("flow-72",
                output.getHeaders().get("businessCorrelationId"));
        assertEquals("http", output.getHeaders().get("source"));
        assertNotNull(output.getHeaders().getId());
    }
}
~~~

This test confirms custom headers are copied when explicitly requested by the application. Do not use it to assert that input and output `id`s must match or differ; `id` is a framework-managed system header.

### 14.2. `copyHeaders` Overwrites, `copyHeadersIfAbsent` Keeps Builder Values

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderPrecedenceTest {

    @Test
    void copyHeadersCanReplaceAnExistingValue() {
        Message<String> output = MessageBuilder.withPayload("result")
                .setHeader("businessCorrelationId", "flow-output")
                .copyHeaders(Map.of(
                        "businessCorrelationId", "flow-input"))
                .build();

        assertEquals("flow-input",
                output.getHeaders().get("businessCorrelationId"));
    }

    @Test
    void copyHeadersIfAbsentKeepsTheBuilderValue() {
        Message<String> output = MessageBuilder.withPayload("result")
                .setHeader("businessCorrelationId", "flow-output")
                .copyHeadersIfAbsent(Map.of(
                        "businessCorrelationId", "flow-input",
                        "source", "http"))
                .build();

        assertEquals("flow-output",
                output.getHeaders().get("businessCorrelationId"));
        assertEquals("http", output.getHeaders().get("source"));
    }
}
~~~

These two tests demonstrate builder precedence. Use them whenever a header "changes value on its own" despite calling `setHeader` with the right name.

### 14.3. Removing a Temporary Header

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderRemovalTest {

    @Test
    void removesTemporaryRoutingHeader() {
        Message<String> input = MessageBuilder.withPayload("hello")
                .setHeader("temporaryRoutingHint", "normalize")
                .build();

        Message<String> output = MessageBuilder.fromMessage(input)
                .removeHeader("temporaryRoutingHint")
                .build();

        assertFalse(output.getHeaders()
                .containsKey("temporaryRoutingHint"));
    }
}
~~~

### 14.4. Testing Header Mapping Across Binders

Unit tests with `MessageBuilder` test only in-JVM logic. They do not verify header serialization across Kafka/RabbitMQ. With Spring Cloud Stream, add integration tests using the test binder or an appropriate test broker:

1. Send a message with an allowlisted custom header.
2. Receive the message in the consumer function.
3. Assert both payload and header have the expected types and values.
4. Test unsupported header types or headers filtered by mappers.
5. Verify sensitive headers never appear at the consumer.

The test binder simulates certain binding semantics, yet it does not replace native header-mapping tests against a real broker when the issue involves serialization or transport.

## 15. Diagnostic Checklist

~~~text
1. Does the header belong to HTTP, Spring MessageHeaders, or native broker metadata?
2. Does the adapter map the header into the Message?
3. Do header name and type match the contract?
4. Is MessageHeaders being mutated directly instead of using a builder?
5. Did a function build a new Message with withPayload without copying headers?
6. Did an intermediate step return a plain payload instead of a Message?
7. Did copyHeaders overwrite a value set earlier?
8. Did setHeaderIfAbsent keep an unintended stale value?
9. Did setHeader(name, null) or removeHeader strip the key?
10. Is the header id/timestamp/replyChannel/errorChannel?
11. Does contentType still match the payload after conversion?
12. Do the binder/header mapper support the key, type, size, and header mode?
13. Are native headers decoded back into Spring MessageHeaders at the consumer?
14. Does the header carry credentials/PII that must be stripped before publishing?
15. Did integration tests exercise the exact production adapter/broker?
~~~

## 16. Quick Troubleshooting Table

| Symptom | First check |
| --- | --- |
| Header present at ingress, lost after function | Look for `withPayload(...).build()` without copying headers |
| Header present in function A, lost in B | Check A's output type and B's input type |
| Header present before publish, lost after consume | Check binder, native header mapping, and serialization |
| Header replaced by another value | Check call order of `setHeader`, `copyHeaders`, `copyHeadersIfAbsent` |
| Cannot add header | Check immutable headers, read-only keys, null values, and key spelling |
| Routing header ignored | Check adapter mapping and version routing contract |
| Wrong `contentType` | Check payload representation and message converter |
| `replyChannel`/`errorChannel` lost over broker | Confirm those are internal headers not serialized by default |
| Header arrives in broker as bytes | Check mapper/decode type at consumer |
| Secret header appears downstream | Check copy-all usage and pre-publish allowlist |

## 17. Hands-On Exercises

1. Create a `Message<String>` with `businessCorrelationId`, `source`, and `contentType`. Replace the payload using `withPayload(...).build()` and observe which headers remain.
2. Update the function to keep an allowlist of headers via `copyHeaders`. Explain why copying all headers across a broker is risky.
3. Write two functions `normalize` and `addMetadata`, both taking and returning `Message<String>`. Chain them with `andThen` and verify headers survive.
4. Replace the first function with `Function<Message<String>, String>`. Explain why the second step can no longer read custom headers directly from the plain payload.
5. Write tests comparing `copyHeaders` and `copyHeadersIfAbsent` when the same key already exists.
6. Use `setHeaderIfAbsent` to generate a default correlation ID; then test inputs with a valid ID and an empty ID.
7. Remove a routing hint using `removeHeader`. Verify the original input message remains unmodified.
8. Try setting `id` and `timestamp` with the builder. Explain why system headers must not be used as business metadata.
9. Write a controller accepting `X-Correlation-Id`, validating it, and mapping it to `businessCorrelationId`. Test missing, valid, and newline-containing headers.
10. Publish a message with a custom header through a Kafka/RabbitMQ test environment. Inspect both raw native headers and the message at the consumer.
11. Update `contentType` after converting a payload from a JSON string to plain text. Observe the consumer's converter.
12. Create a header carrying a fake token. Prove an allowlist blocks the token from moving from an HTTP message onto the broker.
13. Log `message.getHeaders().keySet()` at each boundary to pinpoint where a header drops; ensure full values are never logged.
14. Draft a runbook for "header present before publish yet missing after consume", listing binder, mapper, native headers, and serialization checks.

## Takeaways

- `Message<T>` comprises a payload and `MessageHeaders`; the payload can stay intact even while custom headers are lost.
- `MessageHeaders` cannot be mutated directly. Use `MessageBuilder` to create a new message or modify metadata.
- `withPayload(...).build()` does not automatically preserve custom headers from the input message; use `copyHeaders`, `copyHeadersIfAbsent`, or an allowlist.
- `copyHeaders` and `copyHeadersIfAbsent` have different precedence. Builder call order can cause headers to be overwritten unintentionally.
- `id`/`timestamp` are system headers; `replyChannel`/`errorChannel` are typically internal metadata. Never treat them as business headers to ship across brokers.
- Function composition preserves metadata only when types and message transformations are designed for it. Returning a plain payload drops custom headers from the output contract.
- HTTP headers, Spring `MessageHeaders`, and native broker headers are separate layers requiring proper mapping, serialization, and decoding.
- `contentType` must describe the current payload. Copying an old header after changing representation can break converters.
- Copy headers via an allowlist before crossing trust boundaries; prevent leaking `Authorization`, cookies, credentials, PII, and internal headers.
- Test headers at each boundary; `MessageBuilder` unit tests do not replace integration tests across real binders/brokers.

### Official References

- [Spring Framework — Message Abstraction](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework Javadoc — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework Javadoc — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework Javadoc — MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Cloud Function — Programming Model and Function Composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Function Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/routing.html)
- [Spring Cloud Stream — Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-message-handling.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
