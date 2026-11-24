# MessageConverter and Bidirectional Payload Conversion

## Objectives

In Spring Messaging, `MessageConverter` converts payloads between the Java objects an application works with and a representation suitable for a message. The outbound direction converts an object into a serialized payload; the inbound direction reads the serialized payload into the Java type required by the handler.

After this lesson, you will be able to:

- Distinguish `toMessage` and `fromMessage`.
- Understand the role of `MessageHeaders.CONTENT_TYPE` and MIME types.
- Choose an appropriate converter for String, byte array, JSON, or basic type conversion.
- Know when a converter returns `null` and when it throws `MessageConversionException`.
- Use `CompositeMessageConverter` and `SmartMessageConverter`.
- Distinguish Spring Messaging converters from HTTP, JMS, and AMQP converters.
- Test both conversion directions before connecting to a broker.

## 1. What Problem Does MessageConverter Solve?

A business component typically works with typed objects:

~~~java
OrderCreated event = new OrderCreated("ORD-42", 250000);
~~~

However, when a message crosses a communication boundary, the payload usually needs a transmittable representation, for example:

- A `byte[]` containing JSON or binary data.
- A `String` containing plain text or JSON.
- An encoded protobuf message.
- An XML representation or another format understood by both ends.

On the receiving side, the application needs to turn that payload back into an object matching the handler.

If you hand-write serialization/deserialization in every producer and consumer, business code becomes tightly coupled to the transport format. `MessageConverter` consolidates conversion responsibility into a replaceable or configurable abstraction.

Spring Messaging defines the interface:

~~~java
public interface MessageConverter {

    Object fromMessage(Message<?> message, Class<?> targetClass);

    Message<?> toMessage(Object payload, MessageHeaders headers);
}
~~~

The two methods represent the two directions of the same contract:

| Method | Direction | Input | Result |
|---|---|---|---|
| `toMessage(payload, headers)` | Outbound | Java object and optional metadata | New message with the payload converted to a representation |
| `fromMessage(message, targetClass)` | Inbound | Received message and target Java type | Object of the type the application needs |

`MessageConverter` only converts payloads and creates/reads messages. It does not open network connections, send messages to a broker, persist data, perform TLS encryption, or guarantee delivery.

## 2. The Two Conversion Directions

### Outbound: Java object to transmittable payload

~~~mermaid
flowchart LR
    A["Java Object"] --> B["MessageConverter.toMessage"]
    B --> C["Message<byte[]> or Message<String>"]
    C --> D["Adapter / transport"]
    D --> E["Broker or receiving system"]
~~~

For example, a producer has an `OrderCreated` object. The converter can serialize the object into UTF-8 JSON inside a `byte[]`, while setting `contentType=application/json` in the headers.

The result is still a Spring `Message<?>`; only the payload is converted. Business headers can be passed into `toMessage` to be preserved in the new message.

### Inbound: transmitted payload to Java object

~~~mermaid
flowchart LR
    A["Broker / transport"] --> B["Adapter creates Spring Message"]
    B --> C["MessageConverter.fromMessage"]
    C --> D["Java object by targetClass"]
    D --> E["MessageHandler / method"]
~~~

On the receiving side, the adapter creates a message from protocol data. The converter reads the payload along with its content type and creates an object of the target type.

For example, a message has a JSON bytes payload and `contentType=application/json`; the consumer requests `OrderCreated.class`, so the converter parses the JSON into an `OrderCreated` object.

Both directions must agree on format, charset, schema, and data version. A producer emitting JSON while the consumer treats the payload as plain text will cause errors even when both use the same broker.

## 3. Role of contentType and MIME Types

`MessageHeaders.CONTENT_TYPE` indicates the payload format. Its value is typically a `MimeType` or a parseable MIME type string.

Examples:

| Content type | Common meaning | Suitable converter |
|---|---|---|
| `text/plain` | Plain text | `StringMessageConverter` |
| `application/json` | JSON | `JacksonJsonMessageConverter` or equivalent JSON converter |
| `application/octet-stream` | General binary data | `ByteArrayMessageConverter` |
| `application/xml` | XML | Configured XML converter |
| `application/x-protobuf` | Protocol Buffers data | `ProtobufMessageConverter` with matching MIME type |

You can set the content type with `MessageBuilder`:

~~~java
Message<String> message = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-42\"}")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Or pass headers into `toMessage`:

~~~java
MessageHeaders headers = new MessageHeaders(
        Map.of(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
);

Message<?> encoded = converter.toMessage(orderCreated, headers);
~~~

Content type is a format contract, not a transformation itself. Simply setting `application/json` does not automatically turn a Java object into JSON; the converter performs the serialization.

### When content type is missing or mismatched

Converters extending `AbstractMessageConverter` have a list of supported MIME types and a `ContentTypeResolver`. By default, the resolver reads `MessageHeaders.CONTENT_TYPE`. A converter can also pick a default content type from its first supported MIME type when creating a message that does not yet have one.

`strictContentTypeMatch` defaults to `false`. If `setStrictContentTypeMatch(true)` is enabled, the converter requires the resolver to find a content type matching a supported MIME type; messages without a content type may be skipped by that converter.

If a producer declares `application/json` while the actual payload is non-JSON text, the consumer may throw a parse error. If the wrong charset is declared, accented data or non-ASCII characters may be decoded incorrectly. Set the content type and charset to match the actual bytes.

## 4. Common Converters in Spring Messaging

The classes below belong to package `org.springframework.messaging.converter`. They do not share the same responsibility:

| Converter | Role |
|---|---|
| `SimpleMessageConverter` | Wraps a payload into a message and unwraps the payload if it already matches the target class. Performs no real serialization/deserialization and ignores content type. |
| `GenericMessageConverter` | Extends `SimpleMessageConverter`; uses Spring `ConversionService` to convert an existing payload to the target type. |
| `StringMessageConverter` | Converts String payloads and text representations; supports MIME type `text/plain`. |
| `ByteArrayMessageConverter` | Works with `byte[]` payloads; supports `application/octet-stream`. |
| `JacksonJsonMessageConverter` | Converts Java objects and JSON using Jackson 3.x; available in Spring Framework 7.0 and later. |
| `MappingJackson2MessageConverter` | Jackson 2-based JSON converter. In Spring Framework 7.0, this API is deprecated in favor of `JacksonJsonMessageConverter`. |
| `MarshallingMessageConverter` | Converts XML via Spring OXM `Marshaller` and `Unmarshaller`. |
| `ProtobufMessageConverter` | Converts Protocol Buffers messages. |
| `CompositeMessageConverter` | Tries multiple converters in order until one returns a non-`null` result. |

### SimpleMessageConverter and GenericMessageConverter

These are two easily misunderstood names.

Spring Messaging's `SimpleMessageConverter` only unwraps the payload when it is already compatible with the target class; the outbound direction simply wraps the object in a message. It ignores content type and is neither a JSON converter nor a byte serializer.

`GenericMessageConverter` uses `ConversionService` to perform object type conversion on the inbound direction. For example, it can convert a String payload `"42"` into an `Integer` if `ConversionService` has a suitable converter. Its `toMessage` direction is inherited from `SimpleMessageConverter`, so it still only wraps the payload rather than serializing it into bytes.

If you need to turn an object into JSON bytes, choose a real JSON converter.

### StringMessageConverter and ByteArrayMessageConverter

`StringMessageConverter` handles String and supports `text/plain`. The charset should be consistent across both ends; a charset can be passed into the constructor.

`ByteArrayMessageConverter` handles `byte[]` payloads and `application/octet-stream`. It fits when data has already been encoded elsewhere or when the application wants to preserve raw bytes.

Neither converter understands business structure inside the payload. They handle text or byte representations.

### JacksonJsonMessageConverter

In Spring Framework 7, `JacksonJsonMessageConverter` is the JSON converter based on Jackson 3.x. Its default constructor creates a `JsonMapper` and discovers Jackson modules on the classpath. You can pass a custom `JsonMapper` or a list of supported MIME types.

Example:

~~~java
JacksonJsonMessageConverter converter = new JacksonJsonMessageConverter();

Message<?> outbound = converter.toMessage(orderCreated, null);

OrderCreated inbound = (OrderCreated) converter.fromMessage(
        outbound,
        OrderCreated.class
);
~~~

The snippet above illustrates the API; the project needs Jackson 3 and a suitable `OrderCreated` type to run. In Spring Framework 7, `MappingJackson2MessageConverter` is deprecated as of 7.0 and replaced by `JacksonJsonMessageConverter`. For applications on Framework 6.x still using Jackson 2, use the converter corresponding to your running release line and check that version's Javadoc.

## 5. Does MessageConverter Return null or Throw an Exception?

By the interface contract:

- `fromMessage` returns an object if it can convert the payload to the target class.
- `toMessage` returns a new message if it can convert the payload.
- If the converter does not support the media type or cannot perform the conversion per contract, it may return `null`.

`null` usually means this converter does not handle that payload/format. This is useful when multiple converters are placed in a composite.

If the converter accepted the payload for processing, but the payload is corrupted, JSON is invalid, the charset cannot be decoded, or parsing fails, the implementation may throw `MessageConversionException`. This is a `MessagingException` used to represent conversion errors.

Distinguish between these cases:

| Situation | Typical outcome |
|---|---|
| Converter does not support MIME type | Returns `null` |
| Payload is not of a type the converter supports | Returns `null` |
| Malformed JSON or unparseable data | Throws `MessageConversionException` |
| No converter in composite handles it | Composite returns `null`; caller decides how to report the error |
| Conversion succeeds | Returns target object or new message |

Do not use `null` to represent empty business data if that could be misinterpreted as "converter does not support". Distinguish a valid payload with a null value from a converter declining to handle a message.

## 6. AbstractMessageConverter: Foundation for Building Converters

Many Spring converters extend `AbstractMessageConverter`. This class provides common logic:

- List of supported MIME types.
- Payload class and content type checks.
- MIME type resolution via `ContentTypeResolver`.
- Support for bidirectional conversion and conversion hints.
- Configuration of preferred serialized payload type as `byte[]` or `String`.
- Optional strict content type matching.

Key extension points:

| API | Purpose |
|---|---|
| `supports(Class<?> clazz)` | Determines which payload classes the converter supports. |
| `convertToInternal(payload, headers, hint)` | Converts a Java object into a serialized payload form. |
| `convertFromInternal(message, targetClass, hint)` | Reads a serialized payload into the target object. |
| `getDefaultContentType(payload)` | Selects a default content type when an outbound message lacks one. |
| `setSerializedPayloadClass(byte[].class)` | Selects bytes as the serialized payload form. |
| `setSerializedPayloadClass(String.class)` | Selects String as the serialized payload form. |
| `setStrictContentTypeMatch(true)` | Requires content type to match a supported MIME type. |

In `AbstractMessageConverter`, the default serialized payload class is `byte[]`. Subclasses can change this if needed.

When writing a custom converter, declare specific MIME types and accept only payload classes the converter truly understands. Avoid registering `*/*` indiscriminately because the converter may mistakenly claim messages meant for another converter.

## 7. SmartMessageConverter and Conversion Hints

`SmartMessageConverter` extends `MessageConverter` with two overloads taking an extra `conversionHint`:

~~~java
Object fromMessage(
        Message<?> message,
        Class<?> targetClass,
        Object conversionHint
);

Message<?> toMessage(
        Object payload,
        MessageHeaders headers,
        Object conversionHint
);
~~~

A conversion hint is supplemental information for the conversion process. One example is the `MethodParameter` of a parameter or return value in a handler method. A converter can use the hint to inspect annotations or generic type information that `Class<?>` alone does not fully describe.

Example use cases:

- A handler accepts a collection type with a generic element type.
- A method parameter has an annotation specifying a serialization view.
- A return value carries additional metadata affecting serialization.

Not every converter needs hints. If a converter does not implement `SmartMessageConverter`, the framework can only invoke the basic contract.

## 8. CompositeMessageConverter and Selection Order

`CompositeMessageConverter` holds a list of converters. When receiving or creating a message, it invokes converters in sequence until one returns a non-`null` result.

~~~java
List<MessageConverter> converters = List.of(
        new StringMessageConverter(StandardCharsets.UTF_8),
        new ByteArrayMessageConverter(),
        new JacksonJsonMessageConverter()
);

CompositeMessageConverter composite =
        new CompositeMessageConverter(converters);
~~~

Order matters:

1. The first converter is tried first.
2. If a converter returns `null`, the composite tries the next converter.
3. The first converter returning a result ends the search.
4. If all return `null`, the composite cannot convert that message.

When configuring custom converters, place specialized converters before general ones if both could match the same kind of payload. If an overly broad converter comes first, it may handle the message before a more suitable converter is tried.

A composite does not fix an incorrect content type or turn a malformed payload into a valid one. It only coordinates trying the converters.

## 9. Distinguishing MessageConverter Types in the Spring Ecosystem

The name `MessageConverter` appears across multiple modules, but the interfaces are not the same.

| Type | Package | Scope |
|---|---|---|
| Spring Messaging | `org.springframework.messaging.converter` | Converts Spring `Message` payloads between objects and representations. |
| Spring AMQP | `org.springframework.amqp.support.converter` | Converts objects/Spring messages with AMQP messages and message properties. |
| Spring JMS | `org.springframework.jms.support.converter` | Converts objects/Spring messages with `jakarta.jms.Message` or corresponding JMS messages. |
| Spring MVC / HTTP | `org.springframework.http.converter` | Reads and writes HTTP request/response bodies via `HttpMessageConverter`. |

These interfaces have similar names because they all solve conversion problems, but they belong to different protocol boundaries. Do not pass a converter from the Spring Messaging package into an API expecting a Spring AMQP or JMS converter without a compatible adapter.

For Kafka, Spring Kafka has its own serializers/deserializers and record/message converters. Choosing a Kafka serializer does not mean `org.springframework.messaging.converter.MessageConverter` has been configured.

## 10. Where Are Converters Used in the Messaging Flow?

### Spring WebSocket and STOMP

Spring WebSocket uses converters to translate STOMP message payloads between incoming/outgoing data and Java objects. For example, a client sends JSON to a destination, and the handler method receives the converted object. When the server sends an object to `/topic/orders`, the converter produces a text or byte payload matching the broker configuration.

~~~java
messagingTemplate.convertAndSend("/topic/orders", orderCreated);
~~~

This method uses the converter configured in the application's messaging broker. If you need to change JSON mapping or add a new format, configure the broker's converter list.

### Spring Integration

Endpoints can use converters to convert inbound message payloads into handler method parameter types based on content type. Spring Integration can also use `ConversionService` for simple Java type conversion. These are two related but distinct mechanisms.

### JMS, AMQP, and Kafka

JMS, AMQP, or Kafka adapters usually have their own conversion layer between Spring messages and protocol messages/records. A flow can involve multiple steps:

1. A Spring Messaging converter converts an object into payload bytes.
2. The adapter maps headers to protocol properties.
3. The client sends the message over the protocol.
4. The receiving-side adapter creates a Spring message.
5. An inbound converter converts bytes into an object for the handler.

Do not assume every step uses the same converter. Check the exact module and API being configured.

## 11. Runnable Java 17+ Example: String to Bytes and Back to String

This example uses `StringMessageConverter` to demonstrate both conversion directions. The outbound direction converts a String into a `byte[]` payload; the inbound direction reads bytes back into a String. The program requires neither a broker nor Jackson.

Project structure:

~~~text
message-converter-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageConversionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-converter-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### MessageConversionDemo.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.messaging.converter.StringMessageConverter;

public class MessageConversionDemo {

    public static void main(String[] args) {
        StringMessageConverter converter =
                new StringMessageConverter(StandardCharsets.UTF_8);

        // Choose byte[] as the serialized payload form.
        converter.setSerializedPayloadClass(byte[].class);

        // Outbound: Java String -> Message with byte[] payload.
        Message<?> outbound = Objects.requireNonNull(
                converter.toMessage("hello-spring", null)
        );

        byte[] wirePayload = (byte[]) outbound.getPayload();

        System.out.println("wirePayloadType="
                + wirePayload.getClass().getSimpleName());
        System.out.println("wirePayload="
                + new String(wirePayload, StandardCharsets.UTF_8));

        // Inbound: byte[] payload -> Java String.
        String inbound = (String) Objects.requireNonNull(
                converter.fromMessage(outbound, String.class)
        );

        System.out.println("decoded=" + inbound);
    }
}
~~~

Run from the project directory with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageConversionDemo
~~~

Stdout output:

~~~text
wirePayloadType=byte[]
wirePayload=hello-spring
decoded=hello-spring
~~~

How to read the example:

1. Create a `StringMessageConverter` with the UTF-8 charset.
2. Configure the serialized payload type to `byte[]`.
3. Call `toMessage`: the converter produces a message whose payload is bytes.
4. Read the bytes to inspect the actual content a transport can transmit.
5. Call `fromMessage` with target class `String.class`: the converter decodes the bytes back into a String.
6. The resulting value matches the original because the same converter, charset, and format are used in both directions.

In a real application, the outbound message is sent by an adapter. The consumer receives a new message from the transport and calls `fromMessage`; the example reuses the same message object solely to verify converter round-tripping.

## 12. JSON Example with JacksonJsonMessageConverter

When the payload is a business object, a JSON converter can serialize the object into JSON bytes and deserialize JSON into a Java type.

~~~java
JacksonJsonMessageConverter converter = new JacksonJsonMessageConverter();

Message<?> outbound = converter.toMessage(orderCreated, null);

OrderCreated restored = (OrderCreated) converter.fromMessage(
        outbound,
        OrderCreated.class
);
~~~

This example requires Jackson 3 on the classpath and an `OrderCreated` type that Jackson can map. In Spring Framework 7, the recommended JSON converter is `JacksonJsonMessageConverter`. If you need to configure a naming strategy, date/time module, or custom serializer, create an appropriate `JsonMapper` and pass it into the constructor.

For distributed systems, treat JSON as a data contract between services. Use fields with stable meanings, control schema evolution, and avoid depending on the producer's Java class name. Consumers should handle added or missing fields according to an agreed compatibility policy.

## 13. Common Errors in Payload Conversion

| Symptom | Common cause | How to check |
|---|---|---|
| `fromMessage` returns `null` | Converter does not support payload class or MIME type. | Inspect target class, supported MIME types, and content type. |
| `toMessage` returns `null` | Converter cannot serialize payload or does not support target MIME type. | Check payload class and headers passed in. |
| `MessageConversionException` | Malformed payload, wrong charset, or serializer/deserializer failure. | Inspect raw bytes, charset, content type, and root cause. |
| JSON fails to parse | Producer and consumer disagree on schema, or JSON bytes are corrupted. | Inspect raw payload and JSON parser error. |
| Consumer receives `byte[]` instead of object | Only a byte-array/pass-through converter is active, or JSON converter is not registered. | Check composite converter and Jackson dependency. |
| Object is wrapped as-is | `SimpleMessageConverter` is being used instead of a serializing converter. | Choose a converter matching the actual wire format. |
| String-to-number conversion fails | ConversionService lacks a suitable converter or target type is wrong. | Check `GenericMessageConverter` and ConversionService. |
| Vietnamese characters are corrupted | Outbound and inbound charsets differ, or content type lacks charset. | Use UTF-8 consistently and declare content type accurately. |
| JSON converter cannot be instantiated | Jackson 3 is missing from the classpath or wrong version/module is used. | Check dependency graph and classpath. |
| Converter is not invoked | Adapter/handler uses a different converter or bypasses conversion. | Check the specific module, endpoint configuration, and method argument resolvers. |

## 14. Payload Security and Compatibility

Payload conversion is a trust boundary. Payloads can arrive from external services, clients, or brokers. Several principles apply:

- Limit payload size before parsing to avoid excessive memory consumption.
- Validate data after deserializing; deserializing into an object does not mean the data is valid business-wise.
- Avoid Java native serialization for inter-service messages because it tightly couples producer/consumer to Java classes and increases risk when receiving untrusted data.
- Do not enable Jackson polymorphic default typing indiscriminately. Do not let external data dictate which class to instantiate.
- Control type headers or class names if a converter uses them to choose the target type.
- Do not put secrets or tokens into payloads/headers unnecessarily; apply appropriate encryption and logging policies.
- Design schemas with versioning, rules for adding fields, and rules for handling unknown fields.
- Test compatibility between producer and consumer versions during upgrades.

## 15. Converter Selection and Configuration Checklist

- [ ] Identify the payload object on the producer side.
- [ ] Choose the wire format: text, JSON, bytes, XML, or protobuf.
- [ ] Choose a converter matching the MIME type and target payload class.
- [ ] Set `MessageHeaders.CONTENT_TYPE` accurately.
- [ ] Standardize the charset across both ends.
- [ ] Identify the target class/generic type on the receiving side.
- [ ] Check whether the converter returns `null` or throws `MessageConversionException` on unsupported/invalid data.
- [ ] If using a composite, verify converter ordering.
- [ ] Verify Jackson/serializer dependencies and versions.
- [ ] Test both `toMessage` and `fromMessage`.
- [ ] Test with real payload bytes through the adapter/broker.
- [ ] Validate schemas and enforce payload size limits.
- [ ] Verify the converter belongs to the right module: Messaging, HTTP, JMS, AMQP, or Kafka.

## Key Takeaways

- `toMessage` converts a Java object into a serialized payload; `fromMessage` converts a payload into the target object.
- `MessageHeaders.CONTENT_TYPE` indicates the MIME type used to choose how to read/write the payload.
- `null` usually indicates the converter does not support the message; parse/serialization errors may throw `MessageConversionException`.
- `SimpleMessageConverter` in Spring Messaging only wraps/unwraps; `GenericMessageConverter` uses ConversionService for type conversion.
- `StringMessageConverter`, `ByteArrayMessageConverter`, and `JacksonJsonMessageConverter` handle specific payload formats.
- `CompositeMessageConverter` tries converters in order; `SmartMessageConverter` supports conversion hints.
- Spring Messaging, HTTP, JMS, and AMQP have separate converter interfaces; use the right module API.
- A converter does not send messages over the network. The adapter or transport handles data transmission after conversion.

## Official Documentation

- [Spring Framework Javadoc: MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Javadoc: AbstractMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/AbstractMessageConverter.html)
- [Spring Framework Javadoc: SmartMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/SmartMessageConverter.html)
- [Spring Framework Javadoc: StringMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/StringMessageConverter.html)
- [Spring Framework Javadoc: GenericMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html)
- [Spring Framework Javadoc: CompositeMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/CompositeMessageConverter.html)
- [Spring Framework Javadoc: JacksonJsonMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/JacksonJsonMessageConverter.html)
- [Spring Framework Javadoc: MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html)
- [Spring Framework Reference: HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring AMQP Reference: Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html)
