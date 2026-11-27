# JSON Fails to Convert, Type Mismatch, or Missing contentType

## 1. Identify the Exact Error Before Changing Configuration

In Spring Cloud Stream, `Supplier`, `Function`, and `Consumer` work with messages through input/output bindings. The Kafka, RabbitMQ, or Pulsar binder handles communication with the broker; the message conversion layer is responsible for turning received payloads into the Java type expected by the function. Because of this, "JSON fails to convert" errors can occur at several different stages.

For example, a consumer declares `Consumer<OrderCreated>`, yet the broker delivers a byte sequence, invalid JSON, the wrong content type, a different schema, or a native deserializer returns a type the consumer cannot handle.

Common symptoms:

- `MessageConversionException` or `Cannot convert` errors when the framework converts the payload.
- `JsonProcessingException`, `MismatchedInputException`, `InvalidFormatException`, or Jackson binding errors.
- `ClassCastException` when the handler receives an unexpected type after conversion or performs a manual cast.
- `SerializationException` or Kafka client deserializer errors occurring before the function is invoked.
- The function is invoked, but the payload is an unparsed JSON string instead of a POJO.
- The consumer drops messages or retries endlessly due to an unrecoverable schema error.

Do not fix this by blindly switching every binding to `application/json`. You need to know **which layer failed**, **what the actual payload is**, **which headers are still present**, and **whether the target Java type matches**.

## 2. Message Path and Where Conversion Happens

A processing flow may travel through:

~~~mermaid
flowchart TD
    P[Producer data / Java object] --> E[Encode payload]
    E --> B[(Kafka / RabbitMQ / Pulsar)]
    B --> D[Binder / native deserializer]
    D --> H[Spring Message headers + payload]
    H --> C[Content type / type conversion]
    C --> F[Supplier / Function / Consumer]
    F --> R[Business result or output binding]
    D -. Deserialization failure .-> X[Poll/client error]
    C -. Conversion failure .-> Y[Conversion error]
    F -. Business exception .-> Z[Processing error]
~~~

Distinguish three error groups:

1. **Broker client/deserializer:** fails to read the record into the configured type; the function has not run.
2. **Spring Cloud Stream conversion:** the record was received, but cannot be converted to the function's input type.
3. **Business handler:** conversion succeeded; handler code threw a validation or side-effect error.

These groups follow different retry, error channel, and DLQ paths depending on the binder and version. Fixing the issue properly requires identifying which group the error belongs to.

## 3. `contentType` Is Not the Same as Java Type

`contentType` describes the data format being exchanged, for example:

- `application/json`: payload encoded as JSON.
- `text/plain`: plain text data.
- `application/octet-stream`: binary bytes without a higher-level structural description.
- A MIME type with a converter-specific suffix or parameter, such as `application/json;charset=UTF-8`.

The Java type is the type used by the function, such as `String`, `byte[]`, `OrderCreated`, or `Message<OrderCreated>`.

With a byte payload containing `{"orderId":"O-1"}` and target `OrderCreated`, the framework needs to know the byte format and have a matching converter to instantiate the right object. `application/json` alone does not guarantee success if the JSON does not fit the Java structure.

Conversely, a String payload does not mean the MIME type must always be `text/plain`: a String can be **JSON text** or **an ordinary business string**. The two cases encode differently and must be tested explicitly.

## 4. Precedence Rules for Determining Content Type

In Spring Cloud Stream's standard message conversion mechanism, content type information is typically resolved in this order:

1. The `contentType` header on the message, if validly provided.
2. The `content-type` property of the corresponding binding.
3. The default content type applied by the framework, usually `application/json` in the standard Spring Cloud Stream model.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
~~~

When the producer sends a different content-type header, that header can take precedence over the binding configuration. Therefore, changing YAML to JSON may not fix a message carrying an incorrect `text/plain` header.

Note: this rule applies when Spring Cloud Stream manages conversion. With native Kafka SerDe, Pulsar Schema, or custom converters, conversion may happen earlier or bypass this layer; observe actual behavior for your binder and version.

## 5. Quick Symptom-Based Diagnostic Table

| Symptom | Common Cause | How to Check |
|---|---|---|
| Valid JSON but `ClassCastException` occurs | Function type does not match the created object | Check generic type and actual converter |
| `MismatchedInputException` | JSON array when Java target is an object or vice versa | Compare payload shape against record/class |
| `InvalidFormatException` | JSON field has wrong type, unparseable enum/timestamp | Inspect JSON path and failing value |
| `contentType` header is missing | Producer omitted it, binder header mapping dropped it, or native mode | Inspect headers before conversion and binding config |
| Header is `text/plain` while payload is a JSON object | Producer declared the wrong MIME type | Compare raw bytes against actual headers |
| Message arrives as a `String` containing JSON | Function signature takes String or converter did not build a POJO | Check target type and serialization |
| Kafka `SerializationException` on poll | Native deserializer cannot read the bytes | Check key/value deserializer, SerDe, and wire format |
| A few events fail after deploy | Unhandled schema drift/compatibility break | Compare event versions, fields, and consumer build |
| Fails only when crossing a different broker | Differing header propagation/codecs | Compare raw bytes and MIME headers on both ends |
| Malformed JSON retries forever | Unretryable data error configured as transient | Classify errors, DLT/DLQ, and backoff |

Do not conclude from a single exception class name alone: many exceptions are wrapped by Spring Integration, binder error handlers, or framework retry.

## 6. Running Example: Function Receiving OrderCreated

Define sample data types:

~~~java
record OrderCreated(
    String eventId,
    String orderId,
    long totalCents
) {}

record OrderAccepted(String eventId, String status) {}
~~~

Transformation function:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event ->
            new OrderAccepted(event.eventId(), "ACCEPTED");
    }
}
~~~

Valid JSON message:

~~~json
{
  "eventId": "evt-101",
  "orderId": "ord-101",
  "totalCents": 250000
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

This is the baseline for comparison. When the handler does not receive the record, inspect actual bytes, headers, and target type before modifying business code.

## 7. How Producers Should Send JSON Properly

Producers can emit events in several ways:

- Send a POJO so the converter/binder encodes it based on content type.
- Send encoded JSON bytes and declare content type explicitly when passing a Spring Message.
- Use a broker native serializer; in that case, the wire format must be agreed upon uniformly.

Example constructing JSON byte messages explicitly with Jackson:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

ObjectMapper objectMapper = new ObjectMapper();
OrderCreated event = new OrderCreated("evt-101", "ord-101", 250_000);

byte[] bytes = objectMapper.writeValueAsBytes(event);
Message<byte[]> message = MessageBuilder.withPayload(bytes)
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .setHeader("eventId", event.eventId())
    .build();
~~~

In this snippet, `ObjectMapper` produces JSON bytes and the header declares `application/json`. As the message passes through Kafka/Rabbit/Pulsar, binder and producer settings govern how headers are carried to the broker.

Do not encode an object twice: if the producer already serialized a POJO to a JSON String and a converter then serializes that String as JSON again, the wire format becomes a **quoted JSON string** instead of a JSON object.

## 8. JSON Object and JSON String Are Two Different Wire Formats

Two payloads look similar yet have different semantics:

~~~json
{"eventId":"evt-101","orderId":"ord-101","totalCents":250000}
~~~

~~~json
"{\"eventId\":\"evt-101\",\"orderId\":\"ord-101\",\"totalCents\":250000}"
~~~

The first payload is a JSON object. The second payload is a JSON string whose text happens to look like a JSON object. When the Java target is `OrderCreated`, Jackson will not necessarily convert the second JSON string into an object without custom conversion handling.

In logs, both strings may be escaped differently, making them easy to misread. Check:

1. Is the actual first byte `{` or a double quote `"`?
2. Is the producer sending a POJO, String, `byte[]`, or `Message<?>`?
3. Is there a `writeValueAsString` step followed by another JSON converter?
4. Is the consumer target a POJO or a String?

Fix **the encoding point** instead of adding "double-parse" logic to every consumer, unless temporary compatibility with existing legacy data is required.

## 9. A JSON Array Cannot Convert into a Single POJO

If the producer sends:

~~~json
[
  {"eventId":"evt-1","orderId":"ord-1","totalCents":10000},
  {"eventId":"evt-2","orderId":"ord-2","totalCents":20000}
]
~~~

while the bean declares `Consumer<OrderCreated>`, the JSON root is an array whereas the target is an object. This is a structural mismatch; changing `contentType` cannot fix it.

If the contract really is a record wrapping a list, declare a wrapper:

~~~java
record OrderBatch(java.util.List<OrderCreated> orders) {}

@Bean
Consumer<OrderBatch> processBatch(OrderService service) {
    return batch -> batch.orders().forEach(service::handle);
}
~~~

The corresponding payload must be:

~~~json
{
  "orders": [
    {"eventId":"evt-1","orderId":"ord-1","totalCents":10000},
    {"eventId":"evt-2","orderId":"ord-2","totalCents":20000}
  ]
}
~~~

Do not confuse a business-level JSON batch with Kafka/Rabbit binder batch mode: binder batching emits a collection of messages via a different API with its own header/ack semantics. Choose a clear contract and test it.

## 10. Field Type Mismatches and Schema Drift

Some mismatch examples:

~~~json
{"eventId":"evt-1","orderId":"ord-1","totalCents":"not-a-number"}
~~~

~~~json
{"eventId":"evt-2","orderId":"ord-2","totalCents":null}
~~~

~~~json
{"eventId":"evt-3","orderId":"ord-3","totalCents":999999999999999999999999}
~~~

`totalCents` is a `long`, so non-numeric strings, null, or out-of-range values may fail or trigger coercion depending on Jackson configuration. Do not rely on default coercion to protect business invariants.

Causes to audit:

- A field was renamed while the consumer still uses the old name.
- Type changed from String to number, object to array, or an enum gained a new value.
- Producer published a new schema version before consumers supported it.
- Required field is missing, null, or lost precision.
- Timestamps use a format unsupported by the configured `ObjectMapper`.

Schema compatibility must be an explicit release decision: backward, forward, or full compatibility depending on your upgrade rollout. Test with multiple old/new fixture versions before deploying.

## 11. Java Records, Constructors, and Jackson

Spring Cloud Stream relies on conversion and the corresponding JSON library to instantiate the target POJO. The Java type must have a bindable structure:

~~~java
public record CustomerEvent(
    String customerId,
    String eventType,
    java.time.Instant occurredAt
) {}
~~~

For records, use a Jackson version that supports Java records properly. For immutable classes, provide matching constructors/property names or annotations; for Java time types, ensure the appropriate module and configuration are registered if the project supplies a custom `ObjectMapper`.

Example POJO missing an appropriate creator:

~~~java
class LegacyOrder {
    private final String orderId;

    LegacyOrder(String orderId) {
        this.orderId = orderId;
    }
}
~~~

This class may need `@JsonCreator` and `@JsonProperty`, or can be replaced with a record on supported Java/Jackson versions. Do not turn fields public just to appease the converter if doing so breaks model immutability.

When an error says "no Creators, like default constructor, exist," inspect the target class and `ObjectMapper` instead of assuming the broker delivered corrupted payloads.

## 12. Missing `contentType` Error: Tracing Where the Header Was Lost

Suppose the producer sends valid JSON bytes, yet the consumer does not see `contentType`. Possibilities:

1. The producer sent raw bytes without attaching the header.
2. The producer attached the header, but bridging code rebuilt the message and dropped headers.
3. The header was stored under another name or type due to broker binder header mapping.
4. A non-Spring producer used the native protocol without declaring an equivalent content type.
5. An earlier converter layer transformed the message into another type.

Inspect headers across boundaries:

~~~text
producer Spring Message
  -> broker record headers / AMQP properties / Pulsar metadata
  -> Spring Cloud Stream Message
  -> function parameter
~~~

Not every broker shares the same header propagation mechanism. Some metadata is mapped, while some does not exist or translates differently across binders.

If the topic contract is always JSON, setting `content-type: application/json` on the input binding is the common fallback when headers are absent; still verify there are no conflicting headers and that the target type matches.

## 13. Setting `contentType` Properly in `Message<T>`

When using the Spring Message API:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> jsonMessage = MessageBuilder
    .withPayload("{\"eventId\":\"evt-101\",\"orderId\":\"ord-101\",\"totalCents\":250000}")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .build();
~~~

Here the header is Spring's `MessageHeaders.CONTENT_TYPE` and the MIME value comes from `MimeTypeUtils.APPLICATION_JSON`. That avoids typos when crafting messages manually.

If an existing producer emits a JSON String, verify whether the pipeline serializes the String a second time. When strict control over wire bytes is required, emit `byte[]` produced by `ObjectMapper` and add an integration test that inspects the raw record on the broker.

Do not set the `contentType` header to a Java class name. `com.example.OrderCreated` is not a MIME type.

## 14. Binding `content-type` Is a Fallback, Not a Schema Repair Tool

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

helps define the expected format when the binder applies message conversion. Relaxed binding accepts `contentType`/`content-type` variants in Spring configuration, though you should stick to one style consistently.

It does **not** fix:

- Truncated JSON or non-UTF-8 bytes.
- A JSON array expecting a single POJO.
- A new enum value unsupported by the consumer.
- A class that cannot deserialize because it lacks a creator.
- A misconfigured native Kafka deserializer.
- Avro/Protobuf bytes treated as JSON.

If individual messages carry a wrong `text/plain` header, fix the producer or safely transform headers at a controlled boundary; do not assume the binding property will always override it.

## 15. Inspect the Real Payload Type Instead of Guessing with `toString()`

During diagnosis, use a temporary function accepting `Message<byte[]>` or a raw consumer in a test environment to observe what actually arrives. Example:

~~~java
import java.util.HexFormat;
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<byte[]>> inspectRawPayload() {
    return message -> {
        byte[] bytes = message.getPayload();
        int count = Math.min(bytes.length, 16);
        String firstBytes = HexFormat.of()
            .formatHex(java.util.Arrays.copyOf(bytes, count));

        System.out.printf("payloadLength=%d firstBytes=%s contentType=%s%n",
            bytes.length, firstBytes,
            message.getHeaders().get("contentType"));
    };
}
~~~

This is an illustrative diagnostic bean for test environments; changing `function.definition` can create a new consumer group or alter how messages are consumed. Do not attach diagnostic consumers to a live production group without a formal procedure.

**Security:** log only length, MIME type, a safe eventId, and a tiny byte prefix if policy permits. Raw payloads may contain personal data, tokens, or payment details. In production, prefer hashes/checksums, sizes, and metadata instead of dumping entire messages.

In native mode, `Message<byte[]>` may not receive every wire format if the deserializer already failed before building the message; in that case, read raw records using an appropriate client in an isolated environment.

## 16. Check Byte Order Mark, Charset, and Encoding

Most JSON events use UTF-8. Mismatches you may encounter:

- Producer encodes UTF-16 while declaring UTF-8.
- Payload carries an unexpected byte order mark (BOM).
- A string was encoded in one charset and decoded in another.
- Content type is set to `text/plain` without a charset while the consumer assumes a different encoding.
- Payload is compressed or binary-encoded and then read as JSON text.

Diagnostic example validating UTF-8 bytes before parsing:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

String decodeUtf8(byte[] bytes) throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
}
~~~

This snippet is a test/diagnostic helper, not a replacement for Jackson JSON parsing. If `decodeUtf8` succeeds while POJO conversion fails, investigate JSON structure, types, and schemas rather than wire encoding.

Do not unilaterally change the charset across an entire topic while older producers still emit under the prior contract; manage versioned transitions carefully.

## 17. `String`, `byte[]`, `Object`, and `Message<T>` Have Different Effects

The functional bean signature influences whether the framework decides conversion is needed:

| Signature | Intent | What to Watch For |
|---|---|---|
| `Consumer<OrderCreated>` | Receive converted POJO | JSON shape and target class must match |
| `Consumer<String>` | Receive text | May receive JSON text without constructing `OrderCreated` |
| `Consumer<byte[]>` | Receive raw bytes | Handler is responsible for interpreting bytes when appropriate |
| `Consumer<Message<OrderCreated>>` | POJO with headers | Header mapping and payload type must remain intact |
| `Consumer<Message<byte[]>>` | Bytes with headers | Useful for diagnosis in compatible modes |
| `Function<OrderCreated, OrderAccepted>` | Convert input and output | Verify outbound serialization as well |

Changing the target from `OrderCreated` to `String` can make the exception disappear temporarily while leaving the handler receiving raw JSON without the expected validation or typing. That is not a complete fix.

If you use `Object` or raw `Message<?>`, the framework may lack sufficient target type information to deserialize accurately; handler logic must inspect types safely rather than guessing with casts.

## 18. `ClassCastException` After Conversion

Example of problematic code:

~~~java
@Bean
Consumer<Object> processOrder() {
    return payload -> {
        OrderCreated order = (OrderCreated) payload; // may throw
        System.out.println(order.orderId());
    };
}
~~~

A payload arriving as a `Map`, `String`, or `byte[]` cannot simply be cast directly to `OrderCreated`. If `ClassCastException` occurs only inside the handler, check:

1. Are the functional bean's generic types fully specified?
2. Did raw `Function`/`Consumer` erase type information?
3. Is a custom `MessageConverter` returning a `Map`?
4. Did a bridge or router alter the payload type?
5. Did a native serializer produce a different object than the target type?

The preferred fix is declaring accurate generic types and configuring matching converters/Serdes, avoiding unchecked casts. If multiple schemas must be accepted, introduce a versioned DTO or envelope and map explicitly to your domain model.

## 19. Kafka Binder: Native Decoding Changes Where Errors Surface

In a standard Kafka flow, the Spring Cloud Stream Kafka binder can operate on bytes and run message conversion at the Spring layer. When **native decoding** is enabled, the Kafka client `Deserializer`/SerDe is responsible for building the object before the function is invoked.

Illustrative configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            useNativeDecoding: true
~~~

In that mode, the client value deserializer must match the real wire format. If the producer uses `StringSerializer` while the consumer uses a JSON deserializer or vice versa, failures occur right inside poll before Spring conversion.

Exact property names and placement for key/value deserializers depend on your Spring Cloud Stream Kafka binder, Spring Kafka, and Spring Boot versions. Inspect existing consumer properties rather than adding `content-type: application/json` and hoping it resolves a native error.

Some Kafka error-handling strategies for poll-time deserialization errors require dedicated mechanisms such as `ErrorHandlingDeserializer` and version-specific DLQ/error handler setup. Errors occurring before a Spring `Message` is created may not flow through the Function/DLQ the same way normal processing errors do.

## 20. Kafka Keys and Values Can Use Different SerDes

A Kafka record has an independent **key** and **value**. Sometimes the failure is in the key, yet logs are misread as a JSON payload failure:

~~~text
key bytes:   "customer-42"  -> StringDeserializer
value bytes: {"eventId":"evt-42", ...} -> JSON converter/Deserializer
~~~

If the producer writes keys as raw UUID bytes while consumer config uses `StringDeserializer`, routing and key metadata can break or decode incorrectly even while the JSON value is valid.

When investigating, record:

- Did the exception happen in the key or value deserializer?
- What are `key.serializer`/`key.deserializer` and the corresponding value settings?
- Is there a schema registry, custom serializer, or special wire prefix?
- Does the consumer use native or Spring conversion?
- Could the payload be an older record written before a serializer change?

Do not change the consumer's key deserializer just to make JSON payload processing succeed if the key is still needed for partitioning or business ordering.

## 21. Spring Kafka Type Headers and Type Mismatch Risks

In some setups using Spring Kafka JSON serializer/deserializer, Kafka records may carry type headers naming a Java class. If producer and consumer do not share the same package/class name, or trusted packages restrict it, deserialization fails.

For example, the producer embeds a type header pointing to `com.producer.OrderCreated` while the consumer only has `com.consumer.OrderCreated`. Even when JSON fields are compatible, the consumer cannot load the class named in the header.

Design solutions:

- Use contract types/envelopes independent of Java package names.
- Configure the JSON deserializer with an explicit target class or controlled type mappings.
- Control reading/ignoring type headers per framework version.
- Scope trusted packages narrowly; never open `*` indiscriminately in production.
- Test producers and consumers across two different releases against a real topic.

`contentType` and Spring Kafka type headers are **two separate mechanisms**. Setting `contentType=application/json` does not fix a type header pointing to a nonexistent class.

## 22. RabbitMQ Binder: AMQP Properties and Spring Headers

RabbitMQ uses AMQP message properties, including `content_type`, alongside custom headers. The Spring Cloud Stream Rabbit binder maps this metadata into Spring Message headers upon receipt.

Cases to verify:

- A non-Spring producer omits `content_type` or sets `text/plain` when bytes are actually JSON.
- Producer sends a Java-serialized binary object instead of JSON.
- Producer configures a different serializer than the consumer.
- Messages arrive through the right exchange/queue, but binding `content-type` is unset.
- Queue/group names changed, causing a new consumer to read older messages in a different wire format.

Consumer binding example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          content-type: application/json
~~~

In systems with non-Spring publishers, inspect raw AMQP bodies and properties with an appropriate admin/test client. Do not rely solely on the queue UI screen, as the UI may render bodies as text even when bytes lack an accurate MIME type.

## 23. Pulsar Binder: Schema and Content Type Are Not the Same Thing

The Pulsar client has its own `Schema` mechanism such as `Schema.JSON`, `Schema.STRING`, `Schema.BYTES`, or broker-managed schemas. Native schema configuration governs how producers encode and consumers decode messages.

Example of a native Pulsar client:

~~~java
import org.apache.pulsar.client.api.PulsarClient;
import org.apache.pulsar.client.api.Producer;
import org.apache.pulsar.client.api.Schema;

Producer<OrderCreated> producer = pulsarClient
    .newProducer(Schema.JSON(OrderCreated.class))
    .topic("persistent://commerce/orders/events")
    .create();
~~~

If the consumer expects `Schema.STRING` while the producer uses a JSON schema, the behavior is not identical to Spring Cloud Stream converting JSON bytes by header. You must identify where the schema is enforced (native Pulsar client, binder, or Spring message converter) and what the target type is.

Pulsar message properties do not automatically map one-to-one with Spring `contentType` across all versions and binders. Do not assume Kafka/Rabbit headers carry over unchanged when bridging to Pulsar. Verify schemas and message headers after a real publish/consume round-trip.

## 24. JSON Differs from Avro, Protobuf, and Schema Registry

A topic can hold Avro/Protobuf bytes or a wire format with a prefix, magic bytes, or schema ID. Those bytes cannot be turned into JSON simply by adding `contentType=application/json`.

Example:

~~~text
Actual bytes:
  [wire prefix / schema id][binary Avro payload]

Incorrect assumption:
  contentType = application/json
  targetType  = OrderCreated
~~~

A JSON parse failure on the first byte does not mean the broker corrupted the record. The producer may simply be using a different serializer than the consumer.

Solution:

1. Identify the actual format from the producer and schema registry.
2. Verify schema ID/version, compatibility, and serializer configuration.
3. Choose the matching decoder/SerDe.
4. Apply JSON message conversion only when data is genuinely in JSON or POJO form.
5. Isolate format migrations using separate topics/versions or a tested dual-read process.

Never run `new String(bytes, UTF_8)` and parse JSON on binary format payloads.

## 25. Headers Lost When Forwarding from a Function to StreamBridge

A pipeline receiving `Message<OrderCreated>` and publishing outbound can accidentally drop content type and correlation headers:

~~~java
@Bean
Consumer<Message<OrderCreated>> forward(StreamBridge bridge) {
    return incoming -> {
        bridge.send("outboundOrders", incoming.getPayload());
    };
}
~~~

By sending only the payload, the code loses the incoming message's business headers. If the output depends on MIME headers or event version headers, behavior can diverge from expectations.

Example forwarding **selected** headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;
import org.springframework.cloud.stream.function.StreamBridge;
import java.util.function.Consumer;

@Bean
Consumer<Message<OrderCreated>> forward(StreamBridge bridge) {
    return incoming -> {
        Object correlationId = incoming.getHeaders().get("correlationId");
        MessageBuilder<OrderCreated> builder = MessageBuilder
            .withPayload(incoming.getPayload())
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON);
        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }
        Message<OrderCreated> outbound = builder.build();
        if (!bridge.send("outboundOrders", outbound)) {
            throw new IllegalStateException("Bridge did not accept the message");
        }
    };
}
~~~

Do not blindly copy every consumer/broker header such as ack handles, offsets, or native partition metadata. Select and test the needed business and trace headers. If `correlationId` is null, omit the header or apply an explicit generation rule.

## 26. Verify Actual Binding Names and Destinations

An error reported as "consumer cannot parse JSON" can actually be caused by the consumer reading from a **different topic** after a bean/function rename.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
~~~

The binding name is `processOrder-in-0`, not `input`, unless an alias was declared. If YAML still places conversion properties under `spring.cloud.stream.bindings.input`, they may not affect the binding that is actually running.

Re-check:

- Does `spring.cloud.function.definition` select the right function bean?
- Which topic/queue does `destination` point to?
- Did `group` or subscription name change?
- Which `binder` is selected in a multi-binder application?
- Does an older version of the topic hold differently formatted payloads?
- Is a routing condition sending messages to the wrong function?

During debugging, never delete a group/offset or queue just to "make the error go away." That can cause unplanned data loss or mass reprocessing.

## 27. Retries Cannot Fix Malformed JSON

An invalid JSON payload is usually a **non-retryable** error: reading the exact same bytes repeatedly will keep failing. This differs from an HTTP 503 or database timeout that may recover after a brief interval.

| Error Type | Example | Typical Appropriate Policy |
|---|---|---|
| Invalid JSON syntax | Missing brace, truncated JSON | Non-retryable → DLQ/quarantine |
| Field violates schema | New enum value, incompatible data type | Check compatibility, DLQ if unrecoverable |
| Wrong type header | Class missing / outside trusted packages | Fix serializer/type mapping, inspect existing data |
| Downstream dependency transient error | HTTP 503, timeout, connection reset | Bounded retry with backoff |
| DB conflict with idempotency | Same eventId redelivered | Deduplicate / record business success |
| Broker outage | Dropped connection, leader change | Client reconnect/retry per binder |

Routing all conversion exceptions into retries with a high `maxAttempts` lets one poison message spike CPU, build lag, and stall partition processing. A DLQ entry should preserve enough context—eventId, topic, error, schema version, and timestamp—while keeping sensitive data out of uncontrolled logs.

## 28. Errors Before the Handler Is Called: How Handling Differs

An exception in a native Kafka deserializer can occur during poll, before Spring builds a `Message<OrderCreated>` and before any application handler runs. In that case:

- A `try/catch` inside `Consumer<OrderCreated>` cannot catch the error.
- Retry logic on service methods will not be triggered.
- Binder DLT/DLQ may require dedicated configuration to handle deserialization failures.
- A single corrupt record can block consumer progress if the deserializer/error handler is not configured properly.

To inspect:

1. Read the root stack trace, not only the outermost wrapper exception.
2. Determine whether the failure happens in `poll()`/deserializer or during function invocation.
3. Check consumer native decoding and key/value serializer/deserializer configuration.
4. Review `ErrorHandlingDeserializer` or the error handler mechanism for your Spring Kafka version.
5. Test whether corrupt records are skipped, sent to a DLQ, or hold the offset per approved policy.

Do not commit or skip offsets arbitrarily just to get the consumer "moving again." When a bad message must be quarantined, preserve evidence and support controlled reprocessing.

## 29. Test Binder: Reproducing Success and Failure Deterministically

With the `acceptOrder` functional bean, Spring Cloud Stream Test Binder lets you send JSON bytes to the input destination and assert the output:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(properties = {
    "spring.cloud.function.definition=acceptOrder",
    "spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders.events",
    "spring.cloud.stream.bindings.acceptOrder-in-0.content-type=application/json",
    "spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders.accepted"
})
@Import(TestChannelBinderConfiguration.class)
class JsonConversionTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void convertsJsonBytesIntoOrderCreated() {
        byte[] json = """
            {"eventId":"evt-101","orderId":"ord-101","totalCents":250000}
            """.getBytes(StandardCharsets.UTF_8);

        input.send(
            MessageBuilder.withPayload(json)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build(),
            "orders.events"
        );

        Message<byte[]> result = output.receive(2_000, "orders.accepted");
        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .contains("evt-101", "ACCEPTED");
    }
}
~~~

In this test, the `contentType` header is set explicitly and the binding also declares a fallback. Once the baseline passes, add variants omitting the header, setting the header to `text/plain`, and sending invalid JSON to observe the **actual mechanism** of your project's version.

Test Binder verifies conversion inside the application context, but it does not fully simulate wire headers, Kafka native deserializers, Rabbit AMQP properties, or Pulsar Schemas. Those require separate integration tests against the real broker.

## 30. Testing Error Cases Without Hanging the Test Suite

A practical test matrix:

| Case | Payload | Header | Target | Result to Verify |
|---|---|---|---|---|
| J01 | Schema-valid JSON object | application/json | OrderCreated | Converts successfully |
| J02 | Schema-valid JSON object | No header | OrderCreated | Binding fallback or expected error explained |
| J03 | Schema-valid JSON object | text/plain | OrderCreated | Verify header precedence and converter |
| J04 | JSON array | application/json | OrderCreated | Schema/shape mismatch classified |
| J05 | JSON string wrapping a JSON object | application/json | OrderCreated | No silent double encoding |
| J06 | Wrong field type | application/json | OrderCreated | Clear parse/type error |
| J07 | Avro or compressed bytes | application/json | OrderCreated | Not mistaken for JSON |
| J08 | Valid POJO | application/json | OrderCreated | Function and output behave properly |
| J09 | Older schema event | application/json | OrderCreated | Backward compatibility matches policy |
| J10 | Key bytes with wrong SerDe | Native Kafka mode | Target deserializer | Key error classified properly |

For negative tests through a broker, enforce finite timeouts and avoid infinite retries. Assert the expected outcome—exception, DLQ entry, or rejected message per policy—rather than merely waiting for no output and assuming silence means success.

If tests reuse a group/subscription from a prior run, stale backlog can interfere. Create isolated per-run destinations/groups or reset via safe test-environment procedures.

## 31. Logs and Metrics to Collect When Troubleshooting

Capture enough metadata for analysis without leaking payloads:

- `bindingName`, `destination`, `binderName`, and consumer group/subscription.
- Controlled `eventId` or correlation ID.
- Received `contentType` and binding-level default.
- Payload type before and after conversion where observable.
- Payload length and checksum/hash for reconciliation.
- Error stage: poll/deserializer, conversion, or handler.
- Exception class, JSON property path, and schema version.
- Retry attempt, DLQ destination, and final outcome.
- Kafka topic/partition/offset; Rabbit queue/redelivered flag; Pulsar message ID/subscription where relevant.

Do not attach `eventId` as a high-cardinality metric tag. Use metrics with bounded-cardinality labels such as binding, error category, contentType, and outcome. Granular details belong in structured logs/traces with proper sampling and retention policies.

A helpful dashboard distinguishes `deserialization_error_count`, `conversion_error_count`, `business_error_count`, and `dlq_publish_error_count` using project-defined metric names. Do not assume these are built-in default metrics on every binder.

## 32. Runbook: Fixing JSON Errors in Production

Recommended procedure:

1. **Scope the incident:** identify service/version, binding, topic/queue, start time, and affected message count.
2. **Identify the stage:** did the error happen before the function, during conversion, or inside the handler?
3. **Inspect bytes safely:** payload length, magic prefix/encoding, JSON object/array/string.
4. **Check headers:** message `contentType`, binding `content-type`, native mode.
5. **Check Java types:** function generic signature, record/class, Jackson creators, enum/time fields.
6. **Check serializers:** producer bytes, broker wire format, Kafka key/value SerDe, or Pulsar Schema.
7. **Review recent changes:** schema releases, package renames, header mappings, binder upgrades.
8. **Classify the failure:** malformed event or release-induced mismatch?
9. **Quarantine safely:** bound retries for poison messages; preserve reprocessable events.
10. **Fix at the right layer:** producer encoding, binder config, target type, deserializer, or schema compatibility.
11. **Test:** pass/fail fixtures and corresponding broker integration tests.
12. **Verify post-rollout:** lag drops, error rate returns to baseline, event IDs reconcile, DLQ stops spiking.

Never change groups/offsets, delete queues, skip records, or drop payloads just to silence alerts. Those actions can cause silent data loss.

~~~mermaid
flowchart TD
    A[JSON error alert] --> B{Exception occurred where?}
    B -->|Broker poll| C[Inspect SerDe / schema / native mode]
    B -->|Spring conversion| D[Inspect contentType, bytes and target type]
    B -->|Business handler| E[Inspect validation and side effects]
    C --> F{Wire format matches?}
    D --> F
    F -->|No| G[Fix producer / deserializer / mapping]
    F -->|Yes| H[Check DTO/Jackson/schema compatibility]
    E --> I[Classify retryable vs non-retryable]
    G --> J[Test with real broker]
    H --> J
    I --> J
    J --> K[Reconcile ID, DLQ and lag]
~~~

## 33. Hasty Fixes to Avoid

- Do not cast a `String` to a POJO just to bypass the converter.
- Do not slap `contentType=application/json` onto binary Avro/Protobuf bytes.
- Do not open all trusted packages in the JSON deserializer in production without assessing risk.
- Do not change function input to `Object` just to hide an exception without handling types.
- Do not add "double-parse" logic to every consumer to mask double encoding when the producer can be fixed.
- Do not ignore Jackson exceptions and ack/commit as a success.
- Do not enable infinite retries for invalid JSON.
- Do not dump every failing message into a DLQ without metadata needed to investigate and reprocess.
- Do not dump full sensitive raw payloads into logs.
- Do not switch groups, topics, or subscriptions to sidestep a backlog containing bad messages.
- Do not test only with Test Binder when the defect lives in the Kafka/Rabbit/Pulsar wire layer.

## 34. Diagnostic Checklist Before Closing an Incident

- [ ] Identified the root exception and failing stage.
- [ ] Obtained safe wire byte samples, payload size, and verified encoding.
- [ ] Distinguished JSON object, JSON array, JSON string, and non-JSON bytes.
- [ ] Verified `contentType` header and binding `content-type` following precedence rules.
- [ ] Did not confuse `contentType` with Java class/type headers or broker native Schemas.
- [ ] Functional bean has complete generic types matching the target.
- [ ] Record/POJO/Jackson supports actual fields, constructors, and schema versions.
- [ ] Kafka key/value serializers/deserializers or Pulsar Schemas match the producer.
- [ ] Rabbit AMQP `content_type`/header mapping verified if using Rabbit binder.
- [ ] Bridges/`StreamBridge` preserve critical business headers.
- [ ] Negative tests cover malformed JSON and wrong types.
- [ ] Retry/DLQ policies align with transient vs non-retryable errors.
- [ ] No events lost track due to skipped offsets, group changes, or deleted queues.
- [ ] Post-fix lag/backlog, error rate, and DLQ metrics meet operational criteria.

## 35. Summary

JSON conversion failures in Spring Cloud Stream rarely have a single cause. A message processes cleanly only when **wire bytes, content type, converter/SerDe, and Java target type** align. A missing `contentType` can be resolved at the producer or with a binding-level fallback when the topic genuinely carries JSON; however, malformed JSON structures, schema drift, wrong native deserializers, or incompatible type headers require different fixes.

For Kafka, inspect native decoding, key/value SerDes, and poll-stage errors; for RabbitMQ, inspect AMQP bodies, `content_type`, and queues; for Pulsar, inspect native schemas, topic metadata, and subscriptions. Keep event IDs intact, classify errors before retrying, quarantine poison messages safely, and test with both Test Binder and real brokers. The goal is not merely to silence exceptions, but to restore the message contract and preserve system processing integrity.

## References

- [Spring Cloud Stream — Content Type and Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/content-type-management.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Jackson Databind — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features)
