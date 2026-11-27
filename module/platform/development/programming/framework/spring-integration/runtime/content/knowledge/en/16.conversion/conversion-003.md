# MessageConverter and Message Conversion in Spring Integration

## Lesson Objectives

In **Spring Integration Runtime**, the same business information can appear in multiple representations: a JSON string from HTTP, a byte array from a queue, a Java object in a service activator, or an encoded record to be sent to a broker. A flow only works properly when endpoints accurately agree on **payload type**, **metadata**, and **conversion rules** at each boundary.

After this lesson, you will be able to:

- Explain the role of **MessageConverter** in Spring Messaging and the role of a **transformer** in Spring Integration.
- Identify where conversion happens: inbound/outbound adapters, gateways, handler methods, channels, or explicit transformers.
- Configure a JSON ↔ Java object converter; handle cases where a converter does not support the input or the data is invalid.
- Control **contentType**, encoding, data types, headers, and correlation during message conversion.
- Evaluate the impact of conversion on threading, throughput, transactions, retries, errors, and message stores.
- Test valid data, invalid data, redelivered messages, and concurrent messages.

**Scope:** This lesson focuses on how messages are converted and coordinated at runtime. It does not assume that every protocol adapter uses the exact same converter API.

## 1. When Is Message Conversion Needed?

Example order-intake workflow:

~~~mermaid
flowchart LR
    A["HTTP / broker\nJSON text or bytes"] --> B["Inbound adapter"]
    B --> C["Spring Message\npayload + headers"]
    C --> D["Convert JSON → OrderCommand"]
    D --> E["Service activator\ndomain type"]
    E --> F["Convert OrderEvent → JSON"]
    F --> G["Outbound adapter\nHTTP / broker"]
~~~

A **Spring Message** consists of a payload and a set of headers; for example:

~~~text
Message
  payload: byte[] containing {"orderId":"O-42","amount":125000}
  headers:
    contentType: application/json
    correlationId: checkout-42
    id: ...
    timestamp: ...
~~~

Converting a payload from `byte[]` to a Java object may require:

1. Reading bytes using the appropriate format and charset.
2. Parsing JSON and resolving structure/fields.
3. Creating the **OrderCommand** object.
4. Validating business requirements (for example, `orderId` must not be blank).
5. Deciding which headers to preserve, add, remove, or update.

**Successful deserialization does not mean the data is business-valid.** Valid JSON can still miss required fields, carry a negative amount, or contain an unsupported schema version.

## 2. How Does MessageConverter Differ from Transformer and Serializer?

| Mechanism | Primary Purpose | Typical Boundary |
| --- | --- | --- |
| **MessageConverter** (Spring Messaging) | Converts between **Message<?>** and an object using conversion methods and metadata | Called by an adapter, method resolver, or configured component |
| **Transformer** (Spring Integration) | An endpoint in the flow transforming an inbound message/payload into an outbound one; may use MessageConverter internally | Between two channels, easy to see and trace in the message flow |
| **ConversionService** (Spring Core) | Converts Java types such as String → Integer, enum, or value object via registered converters | Type constraints and parameter conversion; does not replace an arbitrary JSON parser |
| **Serializer/deserializer** | Turns data into bytes/text and back according to a format | I/O, storage, network transmission, broker |
| **Protocol-specific converter** | Converts between a protocol message/record and a Spring Message or object | JMS, AMQP, Kafka, HTTP, and their respective adapters |

The central Spring Messaging interface is **org.springframework.messaging.converter.MessageConverter**:

~~~java
public interface MessageConverter {
    Object fromMessage(Message<?> message, Class<?> targetClass);
    Message<?> toMessage(Object payload, MessageHeaders headers);
}
~~~

- **fromMessage**: takes a message and target class; returns the converted object, or **null** if the converter does not support that case. Actual conversion failures may be reported via exceptions.
- **toMessage**: creates a Spring Message from a payload and headers; may return **null** if unsupported.
- Some converters or integration helpers also support conversion hints, content-type resolvers, and format configuration.

Note: This is an **API contract description**, not a promise that every channel will automatically invoke a `MessageConverter` bean. Registering a bean is only part of the setup; you must wire it into the right adapter/endpoint or invoke it explicitly.

A common point of confusion: **org.springframework.jms.support.converter.MessageConverter** has a similar name but serves JMS `Message` conversion with its own API. Spring AMQP and Spring Kafka also provide protocol-level converters/record converters. Always check the **package, conversion direction, and application point** before configuring.

### Transformer Is an Endpoint in the Flow

A transformer is not limited to data type conversion. It can normalize JSON, extract a field, add or remove headers, enrich content, or turn a command into an event. Meanwhile, a `MessageConverter` typically acts as a **conversion strategy** invoked by an endpoint or adapter.

When you need a clear transition between two steps, a transformer makes it obvious to readers **where conversion lives**, makes attaching an error flow easy, and enables latency measurement. If the adapter already performs appropriate conversion, there is no need to add a transformer just to repeat the same work.

## 3. Deciding Conversion at the Right Boundary

In a real-world flow, **multiple conversions** may occur:

~~~text
Broker record bytes
  → [adapter converter/deserializer]
  → Spring Message<String> or Message<byte[]>
  → [transformer: JSON to OrderCommand]
  → Message<OrderCommand>
  → [service activator: business processing]
  → Message<OrderEvent>
  → [outbound adapter converter or transformer]
  → JSON text / bytes / broker record
~~~

Questions to answer:

- Has the adapter already deserialized into a Java object, or does it only emit bytes/strings?
- What **contentType** and charset did the sender set? Does the content type match the actual payload?
- Does the destination expect **OrderCommand**, a JSON String, or `byte[]`?
- Which headers are transport metadata and which are business data? Does **correlationId** need to propagate?
- Is conversion done in the adapter or in a transformer? Is it accidentally done **twice**?

Usually, it is best to pick **one consistent internal payload representation** (such as an immutable DTO) and convert to transport formats at the system edges. That way, business handlers never have to guess whether a payload is a `String`, `byte[]`, or `Map`.

### Content Type Is Not Absolute Proof of Structure

For example, an **application/json** header indicates the expected format; it does not guarantee valid bytes or that the payload is already a DTO. Conversely, an already-decoded DTO might still carry the old `contentType` if a transformer only returns the payload and the framework copies headers.

Establish a clear policy:

- Verify content type/encoding when receiving external data.
- Strip or update headers describing the old representation when converting to an internal form.
- Set the appropriate content type again when encoding outbound.
- Never infer Java target classes from a type header supplied by an untrusted source without an application-controlled allowlist or schema.

## 4. Example: Using MappingJackson2MessageConverter in a Transformer

Here is a concise example using **Spring Messaging MessageConverter** to handle JSON. Assume the application already has a configured **ObjectMapper** (for example, the Jackson bean provided by Spring Boot) and Spring Integration annotation infrastructure enabled.

Domain payload:

~~~java
import java.math.BigDecimal;

public record OrderCommand(String orderId, BigDecimal amount) {
}
~~~

Declare a dedicated converter using the shared configured Jackson mapper:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.converter.MessageConverter;

@Configuration
class OrderConversionConfiguration {

    @Bean("orderJsonMessageConverter")
    MessageConverter orderJsonMessageConverter(ObjectMapper objectMapper) {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();
        converter.setObjectMapper(objectMapper);
        return converter;
    }
}
~~~

Place conversion in two explicit transformers. One transformer decodes before processing; the other encodes before handing off to the outbound adapter:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.stereotype.Component;

@Component
class OrderConversionEndpoints {
    private final MessageConverter jsonConverter;

    OrderConversionEndpoints(
            @Qualifier("orderJsonMessageConverter")
            MessageConverter jsonConverter) {
        this.jsonConverter = jsonConverter;
    }

    @Transformer(inputChannel = "rawOrders", outputChannel = "readyOrders")
    public OrderCommand decode(Message<?> input) {
        Object value =
                jsonConverter.fromMessage(input, OrderCommand.class);
        if (!(value instanceof OrderCommand order)) {
            throw new MessageConversionException(
                    input, "Unsupported input type or contentType");
        }

        if (order.orderId() == null || order.orderId().isBlank()
                || order.amount() == null
                || order.amount().signum() < 0) {
            throw new MessageConversionException(
                    input, "Invalid OrderCommand data");
        }
        return order;
    }

    @Transformer(inputChannel = "outgoingOrders",
                 outputChannel = "serializedOrders")
    public Message<?> encode(Message<OrderCommand> input) {
        Message<?> output = jsonConverter.toMessage(
                input.getPayload(), input.getHeaders());
        if (output == null) {
            throw new MessageConversionException(
                    input, "Unable to encode OrderCommand into a message");
        }
        return output;
    }
}
~~~

An inbound message can be sent by an adapter/gateway to the **rawOrders** channel:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> raw = MessageBuilder.withPayload("""
        {"orderId":"O-42","amount":125000}
        """)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .setHeader("correlationId", "checkout-42")
        .build();

// Send raw to the rawOrders channel via a configured producer/gateway.
// The decode transformer creates an OrderCommand for the handler on readyOrders.
~~~

**Important implementation notes for this example:**

1. **rawOrders**, **readyOrders**, **outgoingOrders**, and **serializedOrders** are channel names in the flow; wire appropriate producers/consumers. Annotations alone do not create a complete end-to-end business flow.
2. **MappingJackson2MessageConverter** relies on the content types it supports; conversion can return **null** if there is no match. Malformed or unparseable JSON causes conversion failures.
3. The **decode** transformer returns an `OrderCommand` payload. Headers may be forwarded by the framework, but the old **contentType** may no longer accurately represent the internal payload: define a header policy at this boundary.
4. The **encode** transformer returns a full `Message`, letting the converter construct payload/headers per configuration. Do not assume the outbound payload is always a `String`: depending on the converter, it may be **`byte[]`**. Verify the destination adapter's requirements.
5. For newly created **`Message<?>`** instances, verify whether correlation, trace, and business headers are preserved as expected. Do not treat ID/timestamp and special headers as arbitrary copyable data.
6. The example illustrates conversion in Java 17+/modern Spring. In production Spring Integration, you can replace manual transformers with built-in JSON transformers or use adapter-supported converters where appropriate.

### Why Are Null Checks and Validation Critical?

A converter may understand the input type yet fail to convert to the target type, or not support the content type. Distinguish two scenarios:

| Scenario | Example | Response |
| --- | --- | --- |
| Conversion unsupported | CSV text sent to a JSON-only converter | Reject the format/route appropriately; do not force arbitrary casts |
| Corrupted data | JSON missing a brace, bytes with wrong encoding | Record conversion failure, route to error flow/DLQ per policy |
| Parses cleanly but invalid business data | Negative amount, blank `orderId` | Clear validation error; usually do not retry indefinitely |
| Schema changed | Required field renamed | Schema compatibility rules and versioning |
| Payload is already target type | `OrderCommand` entering a stage expecting `OrderCommand` | Skip costly conversion; preserve the type contract |

## 5. ConversionService, Datatype Channels, and Handler Methods

Spring's **ConversionService** converts Java types via registered **Converter** or **GenericConverter** implementations. For example, `String → Long`, enums, or custom value objects depending on configuration.

Spring Integration also provides **datatype channels**: a channel can declare allowed payload types; if a suitable converter is also configured, the framework can attempt to convert payloads to the declared type before dispatch. This is a **channel-level type constraint**, not an automatic parser for arbitrary JSON.

Similarly, when a handler method has a concrete parameter:

~~~java
import org.springframework.integration.annotation.ServiceActivator;

@ServiceActivator(inputChannel = "readyOrders")
public void handleOrder(OrderCommand command) {
    // command already has the expected type per the channel/endpoint contract.
    // Proceed with business processing.
}
~~~

The framework includes argument resolution and can use configured conversions for certain parameter types. **Do not rely on a JSON String magically turning into OrderCommand** simply because the method parameter is typed `OrderCommand`. When data comes from external systems, declare conversion at the right boundary and verify it with integration tests.

### Distinguishing Three Easily Confused Conversion Forms

| Input → Output | Common Appropriate Tool | What Must Be Verified |
| --- | --- | --- |
| `String "42" → Long 42` | `ConversionService` | Number format, null, overflow |
| JSON `String`/`byte[]` → `OrderCommand` | JSON `MessageConverter` or JSON transformer | Content type, charset, schema, validation |
| JMS/Kafka/AMQP record → Spring `Message` | Protocol adapter converter/deserializer | Payload, headers, transport metadata, acknowledgment |

Do not force a cast if the runtime object is still `byte[]`/`String`: casting does not decode data. Conversely, do not serialize to JSON and re-parse just to convert between two Java DTOs when direct mapping expresses the transformation more clearly.

## 6. Headers, Content Type, and Correlation During Conversion

At runtime, messages may carry **messageId**, **correlationId**, **sequenceNumber**, **sequenceSize**, routing info, content type, and adapter-generated metadata. Replacing the payload does not automatically update those headers to reflect the new semantics.

Example flow collecting multiple parts of an order:

~~~mermaid
flowchart TD
    A["Part A: JSON/bytes\ncorrelationId=order-42"] --> CA["Convert payload to DTO A"]
    B["Part B: JSON/bytes\ncorrelationId=order-42"] --> CB["Convert payload to DTO B"]
    CA --> AG["Aggregator\ngroup by correlationId"]
    CB --> AG
    AG --> O["Aggregated result"]
~~~

If conversion accidentally drops **correlationId** or alters it to another value, the aggregator may form incorrect groups, wait indefinitely, or combine the wrong messages. Conversely, copying all transport headers into domain messages can leak old adapter metadata into a new adapter.

A helpful design policy:

- **Preserve** business keys, correlation keys, and approved trace headers.
- **Refresh/remove** content type, payload type, or headers that only apply to the old representation.
- **Do not trust** externally supplied target-class control headers; use an application-controlled allowlist/schema.
- **Distinguish** technical message IDs from business IDs/idempotency keys. Conversion that constructs a new message may change the message ID; never use a technical ID as a business key when deduplicating across retries or systems.
- **Review** outbound adapter header-mapping rules; some headers are meaningful only within the JVM and cannot or should not be sent over the wire unchanged.

For JSON, charset, date/time formats, decimals, enums, nulls, and unknown fields must be agreed upon by both producer and consumer. Without a schema contract, two applications can parse "successfully" yet interpret values differently.

## 7. Thread Safety, Performance, and Conversion at Runtime

Conversion is typically stateless regarding business state, yet **a converter instance can be used concurrently** by multiple endpoints or threads:

~~~text
Producer A -- DirectChannel --┐
                              ├── shared converter --> handler
Producer B -- DirectChannel --┘

ExecutorChannel --> thread pool --> concurrent conversions
Poller / multiple consumers ------> concurrent conversions
~~~

**DirectChannel runs synchronously per send**, which does not mean the consumer overall runs on only one thread. `ExecutorChannel`, pollers with task executors, and multiple application instances increase concurrency further.

Guidelines:

- Configure converters/`ObjectMapper` **before** receiving traffic. Jackson's `ObjectMapper` is generally thread-safe across threads once configured; avoid mutating shared configuration during conversion.
- Do not store mutable fields like **currentMessage**, **lastPayload**, or shared buffers inside a converter without proper synchronization. Prefer local variables and immutable DTOs.
- Do not use shared **SimpleDateFormat** instances in custom converters without protection; use immutable **java.time** formatters or proper Jackson configuration.
- JSON mapping, validation, and copying data consume CPU and allocate memory. Measure message size, latency, allocation rate, and executor saturation before increasing concurrency.
- For large messages, consider size limits, streaming parsers, or an appropriate binary format. Never dump full large payloads into logs when conversion fails.
- For third-party converters whose thread-safety is unclear, check the API contract or test concurrent access; **being a singleton bean does not automatically make mutable code thread-safe**.

### Example of an Error-Prone Custom Converter

~~~java
// Not safe if multiple threads invoke concurrently:
class UnsafeConverterState {
    private String currentOrderId;

    void convert(String json) {
        currentOrderId = extractOrderId(json);
        // Another thread can overwrite currentOrderId here.
        publish(currentOrderId);
    }

    String extractOrderId(String json) { return json; }
    void publish(String id) {}
}
~~~

In a safer converter/transformer, **orderId** is a local variable per invocation; shared dependencies hold state only when explicitly designed and synchronized at the right scope.

## 8. Conversion Errors, Transactions, and Retries

Placing conversion before business handlers rejects malformed messages early. However, where conversion sits also affects **how errors surface and how retries behave**.

| Where Conversion Occurs | Where Errors Typically Go | What to Watch For |
| --- | --- | --- |
| Synchronously via `DirectChannel` | Exception typically propagates to the `send` caller | If the sender has a transaction on the same thread, errors can roll back the transaction per configuration |
| After `ExecutorChannel` | Error occurs on a worker thread | Caller's `send` may already have returned; requires an appropriate error flow/`errorChannel` |
| Inside a polling consumer | Error surfaces during poll/handler execution | Check poller transaction, retry advice, and how the source handles redelivery |
| Inside an inbound adapter/deserializer | May fail before building a standard Spring Message | Error routing, ack, and DLQ depend on the adapter/broker |
| Inside an outbound adapter | Internal message may already be processed before encoding | Decide retry, idempotency, and duplicate event emission handling |

A well-behaved converter should **throw a meaningful error** when the payload is invalid; do not swallow exceptions and return empty data as if conversion succeeded. For unsupported formats, reject explicitly or route to an intentional fallback branch.

### What Does Retrying Conversion Mean?

- **Invalid JSON or incompatible schema**: retrying the same bytes usually will not help; consider quarantine/DLQ, observability, and fixing upstream data.
- **Transient errors** in an auxiliary lookup step (if conversion calls an external service): retrying with backoff may work, though conversion is then no longer a pure transformation; consider separating I/O from the converter.
- **Failures after conversion and side effects**: retries can reprocess the same message; design **idempotency** using business keys, unique constraints, or an outbox/inbox pattern.
- **Transactions**: DB rollback does not undo all external side effects, and a transaction bound to the producer's thread does not automatically continue across an `ExecutorChannel`.

If messages are placed into a **MessageStore**, know whether the store persists payloads **before or after conversion** and which serializer the persistent store uses. Changing schemas/classes in a new application version can make old stored messages unreadable. For groups/aggregators, correlation and expiry metadata must also survive conversion.

## 9. Testing Conversion Against the Flow Contract

At a minimum, test these scenario groups:

1. **Happy path:** Valid JSON `String` or `byte[]` with `application/json` header converts into a DTO with expected values.
2. **Unsupported input:** Unknown content types or unsupported payloads produce a well-defined outcome (`null`/exception/fallback).
3. **Malformed payload:** Syntactically invalid JSON, missing fields, wrong types, unexpected charset.
4. **Business validation:** Negative amount, blank `orderId`, or duplicate key; distinguish from parse errors.
5. **Header contract:** `correlationId`, business keys, and trace headers are preserved/updated properly; `contentType` is not left stale after representation changes.
6. **Outbound round trip:** DTO → serialized message → DTO can be read back; verify actual adapter content and `byte[]`/`String` type.
7. **Concurrency:** Distinct messages passing through the same converter bean do not mix data or state.
8. **Retry/redelivery:** Replaying the same `requestId` does not create duplicate business side effects; conversion errors route to the expected error flow.
9. **Compatibility:** Old/new producers work with consumers per schema policy; verify messages remaining in a persistent store during upgrades.

Pseudo-test example verifying round-trip behavior:

~~~java
Message<String> input = MessageBuilder
        .withPayload("""
                {"orderId":"O-42","amount":125000}
                """)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();

Object decoded = jsonConverter.fromMessage(input, OrderCommand.class);
assert decoded instanceof OrderCommand;
assert ((OrderCommand) decoded).orderId().equals("O-42");

Message<?> encoded =
        jsonConverter.toMessage(decoded, input.getHeaders());
assert encoded != null;
assert encoded.getPayload() != null;

// Do not assert payload is String when the converter may output byte[].
~~~

This illustrates test logic assuming **jsonConverter** is initialized from the configuration above; in real tests, use an assertion library/JUnit and also verify error cases, headers, and runtime channels.

### Diagnosing Production Flow Failures

When a message "reaches the channel but the handler does not receive the right data," check in order:

1. What is the **actual** payload type entering each endpoint? `byte[]`, `String`, `Map`, or DTO?
2. Does the **contentType** header match the payload and the selected converter?
3. **Where** is the converter configured, and which component actually invokes it?
4. Does the converter return **null**, throw an exception, or return an object of the wrong type?
5. Does the transformer properly preserve business/correlation headers?
6. Does the message path pass through an **ExecutorChannel**, poller, retry advice, or async adapter? Does the error flow receive failures?
7. How many times was the message retried/redelivered, and which idempotency key identifies a single business operation?
8. Do error counts grow with payload size/CPU, or only under high concurrency? Check thread safety, pool saturation, and conversion latency.

Log the channel/endpoint name, payload type, `contentType`, `correlationId`, business key, exception class, and concise root cause. Avoid logging full raw payloads containing personal data or secrets.

## 10. Design Checklist

- Define the **data contract** at every boundary: payload type, format, charset, version, null/optional fields.
- Distinguish **Spring Messaging MessageConverter**, **Spring Integration transformer**, and protocol converters.
- Know for sure whether conversion occurs in the **adapter, channel, method resolver, or transformer**; avoid accidentally stacking multiple conversions.
- Control **contentType**, **correlationId**, and type metadata when changing representations.
- Reject unsupported or malformed payloads with explicit errors; separate non-recoverable errors from transient ones.
- Design immutable DTOs and keep converters free of per-message state; test concurrent invocations.
- Audit transactions, ack/retry behavior, and error flows at **thread boundaries**.
- Account for duplicates, persistent message stores, and schema evolution before running flows long term.
- Measure latency, throughput, and memory by payload size; avoid unnecessary deserialization/serialization cycles.

## Conclusion

**MessageConverter** bridges a Spring `Message` and the data representation needed by a processing component; a **transformer** is an explicit processing step in the message flow that can use a `MessageConverter` or custom transformation logic. To keep conversion safe at runtime, define the exact application point, payload/header contracts, error handling, and concurrency scope. When a flow includes pollers, executors, transactions, retries, message stores, or aggregators, a conversion error is not just a parse error: it can affect routing, correlation, recovery, and business consistency.

## References

- [Spring Framework Javadoc — MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Javadoc — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html)
- [Spring Integration Reference — Message Transformers](https://docs.spring.io/spring-integration/reference/transformer.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
