# Precedence Order for Selecting contentType from Header, Binding, and Default

Spring Cloud Stream needs to know the payload format to choose how to convert data between Java objects and the data transmitted over Kafka, RabbitMQ, or Pulsar. This format information is represented by `contentType` (media type). When a message is sent or received, the framework selects `contentType` in precedence order: **message header**, then **binding configuration**, and finally the **application default value**.

This order is critical when a stream has multiple producers, when a function changes payload types, or when an application shares a binding across different formats. If a stale header no longer matches a new payload, the framework may pick the wrong converter and cause conversion errors even when the binding configuration looks right.

## 1. What Is contentType?

`contentType` describes the format and content type of a payload. Values generally follow media type syntax, consisting of a type and subtype, sometimes with additional parameters:

| Value | Common meaning |
|---|---|
| `application/json` | Payload is represented as JSON. |
| `text/plain` | Payload is plain text. |
| `application/octet-stream` | Binary data not tied to a specific application format. |
| `application/avro` | Payload uses Avro format when the application has configured a corresponding converter/serializer. |
| `application/xml` | Payload is represented as XML when an appropriate converter is present. |
| `application/json; charset=UTF-8` | JSON with a specified charset parameter. |

In Spring Messaging, a `Message<T>` consists of a payload and headers. The `contentType` header is metadata describing how to interpret the payload. In binding configuration, the `content-type` property declares the default format for that binding. If neither provides a value, Spring Cloud Stream uses the application's default content type, normally `application/json`.

`contentType` is information used to select a conversion mechanism. It does not define a business schema by itself, does not guarantee the payload is valid, and does not automatically install converters for Avro, Protobuf, or XML. The corresponding converter or serializer must still be present and properly configured.

## 2. Precedence Order for Selecting contentType

Spring Cloud Stream checks three sources in order from highest to lowest precedence:

| Precedence | Source | When is it used? | Example |
|---|---|---|---|
| 1 – highest | Message `contentType` header | Message carries a valid content type header. | `text/plain` |
| 2 | Binding property `content-type` | Message does not have a content type header. | `application/json` |
| 3 – lowest | Default content type | Message has no header and binding does not declare content type. | Default `application/json` |

You can remember the rule as:

```text
message header contentType
          |
          v
binding content-type
          |
          v
spring.cloud.stream.default.contentType
          |
          v
default: application/json
```

A higher-precedence source determines the content type used for that conversion. Lower-level values serve as fallbacks when no higher-level value is provided.

### Selection Examples by Case

Suppose the output binding is configured as `application/json`:

| Message header | Binding `content-type` | Default | Selection result |
|---|---|---|---|
| `text/plain` | `application/json` | `application/json` | `text/plain` from header |
| None | `application/json` | `text/plain` | `application/json` from binding |
| None | Not declared | `text/plain` | `text/plain` from default |
| None | Not declared | Not customized | Default `application/json` |

A present header has higher precedence than binding configuration. Therefore, setting `content-type: application/json` in YAML does not guarantee the JSON converter will be chosen if the message carries a `contentType: text/plain` header.

## 3. First Source: Message contentType Header

The header is the highest-precedence source. An application can attach a content type to a message when creating data or when a function constructs an output message.

Example creating a text message:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> message = MessageBuilder
    .withPayload("Order order-9001 has been created")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
    .build();
```

The `MessageHeaders.CONTENT_TYPE` header describes the payload as `text/plain`. If this message is sent over a binding configured with `content-type: application/json`, the content type from the header still takes precedence. The framework will select conversion matching `text/plain`, provided a suitable converter exists.

A function can also change the payload and update the content type:

```java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Function<OrderPlaced, Message<String>> renderOrder = order ->
    MessageBuilder.withPayload(
            "Order " + order.orderId() + ", total=" + order.totalAmount())
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
        .build();
```

Here, the function converts from `OrderPlaced` to `String`, so the output header is set to `text/plain`. Downstream consumers must receive the content under the corresponding text contract.

### Be Careful When Copying Headers

When a function receives `Message<T>`, copying all headers to the new message may preserve the old payload's `contentType`. If the payload format has changed while the header stays unchanged, downstream converters will interpret the payload under the wrong format.

For example, the input is JSON but the output is plain text. When building the new message, override the content type:

```java
Message<String> output = MessageBuilder
    .withPayload("Order " + input.getPayload().orderId())
    .copyHeaders(input.getHeaders())
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
    .build();
```

Avoid copying headers blindly when the payload changes. Review which metadata remains accurate for the new message, especially content type, schema version, and routing headers.

## 4. Second Source: Binding content-type

If the message does not have a `contentType` header, Spring Cloud Stream uses the binding's `content-type` property. This configuration is appropriate when all messages passing through a binding follow the same format.

Example configuring JSON for input and output:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.placed
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

When a message enters `enrichOrder-in-0` without a content type header, the binding supplies `application/json` for conversion. On the output side, if the function returns a payload without a content type header, the `enrichOrder-out-0` binding supplies the configured format.

Different content types can be configured for input and output. For example, a function that receives JSON and emits plain text:

```yaml
spring:
  cloud:
    function:
      definition: describeOrder
    stream:
      bindings:
        describeOrder-in-0:
          destination: orders.events
          content-type: application/json
        describeOrder-out-0:
          destination: orders.audit-text
          content-type: text/plain
```

This expresses the contract for each stage: input is JSON, output is text. If the function returns a `Message` with its own content type header, that header still takes precedence over the binding property.

## 5. Third Source: Default Content Type

When a message has no content type header and the binding also does not declare `content-type`, Spring Cloud Stream uses the default content type. The usual default value is `application/json`.

You can change the application-wide default content type with the `spring.cloud.stream.default.contentType` property:

```yaml
spring:
  cloud:
    stream:
      default:
        contentType: application/json
```

When this property is not set, the framework uses `application/json`. Defaults have broad scope, so only change them when most bindings in the application genuinely use the same format. For bindings with distinct contracts, declaring `content-type` explicitly is usually easier to read and maintain.

The default content type does not override headers or binding configuration. It is only used when the two higher-precedence sources do not provide a content type.

## 6. Precedence Order Applied on Outbound and Inbound Flows

Content type participates in data conversion in both directions:

### Outbound direction (producer)

1. A function or application component creates a payload or `Message<?>`.
2. The framework determines content type from header, then binding property, then default.
3. A matching message converter transforms the payload into wire format.
4. The binder sends the converted data to the broker destination.

If a header states `text/plain` while the actual payload is a JSON object, the selected converter may not match the data. Ensure the header accurately describes the payload before sending.

### Inbound direction (consumer)

1. The binder receives data from the destination and creates a message for the input binding.
2. The framework determines content type from the forwarded message header, binding configuration, or default.
3. A converter is selected to transform wire data into the payload type requested by the function/consumer.
4. If the data does not match the converter or target type, conversion may fail before the business function is invoked.

A header can only participate in selection on the receiving side if it is preserved or mapped onto the message by the broker and binder. Not every broker/binder propagates all headers in the same way. If the content type header is not forwarded, the binding property or default on the receiving side is used.

## 7. Content Type and MessageConverter

Once the content type is determined, Spring Cloud Stream uses an appropriate message conversion mechanism. The converter recognizes the media type and target type to translate data between wire representation and application objects.

Some examples:

| Content type | Common application payload | Notes |
|---|---|---|
| `application/json` | Java record/POJO, `Map`, collection | Requires an appropriate JSON converter; schema compatibility is still required. |
| `text/plain` | `String` | Data must follow charset conventions and contain text content. |
| `application/octet-stream` | `byte[]` | Application is responsible for interpreting the bytes. |
| `application/avro` | Avro object or converter-supported form | Requires Avro converter/serializer configuration and schema. |
| `application/xml` | POJO or XML representation | Requires an appropriate XML converter. |

If no converter supports the chosen content type or conversion to the target type fails, the framework may throw a conversion error. Merely changing the header from `application/json` to `application/avro` does not turn JSON bytes into Avro; the content must be serialized in the proper format.

Content type can also carry parameters such as charset. For text data, producers and consumers should agree on a charset, typically UTF-8. When processing binary data, never decode bytes into strings with an arbitrary charset.

## 8. Example of Resolving Converter Across Three Levels

Suppose an application has JSON configured as the default:

```yaml
spring:
  cloud:
    stream:
      default:
        contentType: application/json
      bindings:
        publishReport-out-0:
          destination: reports.output
          content-type: application/json
        publishText-out-0:
          destination: reports.text
```

Three messages produce the following outcomes:

**Message A – with header:**

```java
Message<String> textMessage = MessageBuilder
    .withPayload("Daily report is ready")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
    .build();
```

If sent through `publishReport-out-0`, the `text/plain` header takes precedence over the binding's `application/json`.

**Message B – no header, binding has content type:**

```java
streamBridge.send("publishReport-out-0", reportObject);
```

Because the message carries no content type header, the `publishReport-out-0` binding selects `application/json`.

**Message C – no header, binding has no content type declared:**

```java
streamBridge.send("publishText-out-0", "Report generated");
```

The `publishText-out-0` binding declares no content type, so the default `application/json` is selected according to the example configuration. If plain text is desired, set `content-type: text/plain` on the binding or attach a `text/plain` header to the message.

This example shows that a `String` payload does not automatically mean the content type will be `text/plain`. Format selection still follows the precedence order described above; Java types and content types must be designed consistently.

## 9. Common Errors When contentType Mismatches

### Stale header overrides binding

A function receives a JSON message, copies headers, and changes the payload to a string but forgets to update `contentType`. The old header can still override the output binding's `text/plain` configuration. The converter receives JSON metadata while the new payload is plain text.

**Resolution:** when changing payload type, reset `MessageHeaders.CONTENT_TYPE` or remove the old header if you want the binding/default to decide.

### Assuming binding always has highest priority

The development team configures `content-type: application/json`, yet the producer sends a message carrying a `text/plain` header. The header has higher precedence, so the binding is not the selected source.

**Resolution:** inspect actual headers at the send boundary and identify which component creates or copies them.

### Payload and content type describe different formats

An application sets the `application/avro` header while still sending a JSON string. The framework picks a converter for Avro and conversion may fail.

**Resolution:** ensure the serializer produces the declared format; content type only describes data and does not perform transformation in place of a serializer.

### Assuming headers always cross the broker

A producer sets a content type header, but the binder or broker does not propagate that header as expected. The consumer does not see the header and selects content type from its binding or default.

**Resolution:** check the binder's header mapping, native encoding/decoding settings, and the actual received message. For stable contracts, declare binding content type explicitly on the consumer side.

### Using default for bindings with different formats

An application changes the default to `text/plain` to serve a text flow, unintentionally affecting other bindings that do not declare a content type.

**Resolution:** keep the default aligned with the majority of flows and explicitly declare content type on bindings with distinct formats.

## 10. Notes When Using Native Encoding and Native Decoding

Some binders allow the broker client to perform native serialization/deserialization instead of Spring Cloud Stream's message conversion. For example, the Kafka binder has options such as `useNativeEncoding` on the producer side and `useNativeDecoding` on the consumer side.

When native encoding/decoding is enabled, the configured client or broker serializer/deserializer may handle payload conversion. In that case, do not assume Spring's message converter will process data along the usual path based solely on `contentType`. Serializers/deserializers, data types, and schemas must be configured consistently on both sides.

Content type can still be useful as metadata describing the data, but it does not replace native serializer/deserializer configuration. Specific property names and behavior differ by binder, so consult the documentation for the exact binder and version in use.

## 11. Testing contentType Precedence

You should test each precedence source rather than only testing the default case:

| Case | Setup | Expected verification |
|---|---|---|
| Header overrides binding | JSON binding, text/plain header | Converter/format is chosen according to header. |
| Binding overrides default | No header, text/plain binding, JSON default | Binding value is used. |
| Default is used | No header, no binding content type | Configured default is used. |
| Unsupported header | Header points to media type without converter | Clear conversion error occurs rather than silently treating payload as another format. |
| Stale header after payload change | Copy old header then change payload type | Verify header is replaced or removed properly. |
| Header across broker | Send and receive using real binder | Verify header is mapped/preserved as expected. |

Spring Cloud Stream Test Binder is useful for testing function logic, bindings, and message headers within application scope. However, it does not fully simulate header mapping and native serialization of Kafka, RabbitMQ, or Pulsar. Broker-dependent behaviors should be verified with integration tests against the corresponding binder.

When investigating conversion errors, record the binding name, selected content type, payload type before conversion, target type, and root cause from the converter. Avoid logging entire payloads if they contain sensitive data.

## 12. Process for Identifying contentType on Errors

When a message is not converted as expected, check in order:

1. Does the message have a `contentType` header? If so, what are the header's value and data type?
2. Was the header created at the producer, copied from a prior message, or mapped by the binder from the broker?
3. What `content-type` does the current binding declare?
4. If both header and binding omit it, what is `spring.cloud.stream.default.contentType` set to?
5. Is the corresponding converter registered and does it support both the media type and the target payload type?
6. Is the actual payload in the format described by the content type?
7. Does the binder enable native encoding/decoding, causing a different conversion path?
8. On the receiving side, is the header still present, or is the consumer relying on binding properties/default?

The header → binding → default order helps Spring Cloud Stream choose a consistent content type during message conversion. By understanding which source wins and ensuring metadata always accurately describes the payload, development teams can avoid most wrong-converter selection errors and keep data contracts stable across services.
