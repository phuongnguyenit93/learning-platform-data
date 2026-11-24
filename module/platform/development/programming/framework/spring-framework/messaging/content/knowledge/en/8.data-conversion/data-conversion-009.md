# Writing a Custom Converter and Defining Support Conditions in Spring Messaging

Spring Messaging represents data sent across channels using `Message<?>`, while payloads in an application can be DTOs, strings, byte arrays, or custom data types. When converting between Java objects and transmittable data forms, we use **MessageConverter**.

A custom converter must answer two questions:

1. **Which Java types does it support?** For example, only `OrderCommand`, or both `OrderCommand` and `OrderReply`.
2. **Which content formats does it support?** For example, `text/plain`, `application/json`, or a custom MIME type.

Defining support conditions accurately helps Spring choose the right converter and avoids misconverting payloads or misinterpreting message formats.

## 1. MessageConverter in Spring Messaging

The `org.springframework.messaging.converter.MessageConverter` interface has two methods:

```java
public interface MessageConverter {

    Message<?> toMessage(Object payload, MessageHeaders headers);

    Object fromMessage(Message<?> message, Class<?> targetClass);
}
```

- `toMessage`: converts a Java payload into a `Message<?>`, typically including the serialized payload and a `contentType` header.
- `fromMessage`: reads the message payload and converts it into the Java type requested by the caller.

For example, an application has a DTO:

```java
public record OrderCommand(String orderId, int quantity) {}
```

When sending over a transport that accepts only strings or byte arrays, the converter can turn the DTO into a wire-format string. On the receiving side, the converter reads that string and restores it into an `OrderCommand`.

`MessageConverter` only defines the conversion contract. It does not send messages through channels, route messages, or guarantee that a message was processed by a consumer.

## 2. Choosing How to Implement a Converter

There are two common approaches:

- **Implement `MessageConverter` directly:** suitable when full control over message creation, header inspection, and conversion is needed.
- **Extend `AbstractMessageConverter`:** suitable for most custom converters. The base class manages supported MIME types, content types, convertibility checks, and invoking conversion hooks.

`AbstractMessageConverter` implements `SmartMessageConverter`, so it also supports receiving conversion hints. When you only need a standard converter, start from `AbstractMessageConverter` to reduce boilerplate code.

## 3. Defining Support Conditions

### Java types: supports(Class<?>)

When extending `AbstractMessageConverter`, implement:

```java
@Override
protected boolean supports(Class<?> clazz) {
    return OrderCommand.class == clazz;
}
```

This condition determines which Java types the converter can handle. `supports` is used both when converting payloads to messages and when converting messages to target types.

Multiple types can be supported:

```java
@Override
protected boolean supports(Class<?> clazz) {
    return OrderCommand.class == clazz
            || OrderReply.class == clazz;
}
```

Check exact types or a clearly defined set of types. Returning `true` for every class can cause the converter to accept a payload it does not know how to serialize or deserialize, leading to runtime errors.

If supporting subtypes, consider `OrderCommand.class.isAssignableFrom(clazz)`. Use this condition only when the converter truly understands the structure of every subclass; accepting subclasses does not guarantee their formats are compatible.

### MIME types: supportedMimeTypes

A converter typically supports one or more MIME types. `AbstractMessageConverter` accepts a list of MIME types via its constructor:

```java
super(MimeTypeUtils.TEXT_PLAIN);
```

Or supports multiple formats:

```java
super(
        MimeTypeUtils.TEXT_PLAIN,
        MimeTypeUtils.APPLICATION_JSON
);
```

These MIME types describe the data formats the converter can read or produce. The `MessageHeaders.CONTENT_TYPE` header carries the MIME type of the message payload.

Examples:

- `text/plain`: plain text strings.
- `application/json`: JSON.
- `application/octet-stream`: binary data.
- `application/vnd.example.order+json`: custom MIME type for an application's JSON schema.

Do not declare MIME types broader than the formats the converter actually supports. For example, a converter that only serializes `orderId|quantity` strings should not claim to be a JSON converter.

### strictContentTypeMatch

`AbstractMessageConverter` provides the `setStrictContentTypeMatch(boolean)` setting.

- When strict matching is enabled, the converter converts only if the content type is compatible with a supported MIME type. If content type is missing or its MIME type does not match, the converter declines the message.
- When strict matching is disabled (the default), the converter may be considered even if the content type does not match or is unspecified. This is more flexible, but the converter must inspect the actual format carefully.

For protocols with explicit contracts, enabling strict matching helps reject messages with the wrong content type early:

```java
setStrictContentTypeMatch(true);
```

Compatible MIME types can include parameters such as charset. When comparing, Spring applies MIME type compatibility rules rather than raw string equality alone.

## 4. AbstractMessageConverter Conversion Hooks

Two key hooks:

```java
protected Object convertToInternal(
        Object payload,
        MessageHeaders headers,
        Object conversionHint);

protected Object convertFromInternal(
        Message<?> message,
        Class<?> targetClass,
        Object conversionHint);
```

- `convertToInternal`: converts a Java object into an outbound payload, such as a DTO into a JSON string or byte array.
- `convertFromInternal`: converts a message's payload into the target Java type.

The base class performs support-condition checks before calling the hooks. If the converter does not support the Java type or MIME type, the conversion method can return `null` to allow another converter to be tried.

Distinguish two situations:

- **Unsupported:** the converter does not accept that Java type or content type; returning `null` signals that it cannot convert.
- **Malformed data:** the converter accepted a message within its scope, but the payload is invalid; throw a meaningful conversion exception rather than returning `null` as if the converter did not support it.

This distinction helps surface corrupted data instead of silently ignoring it.

## 5. Example: Custom Converter for OrderCommand

The following example uses an `orderId|quantity` wire format and MIME type `text/plain`. This is a simple illustrative format; in real systems, consider escaping, versioning, and schemas if data may contain delimiters or evolve over time.

Create file `src/main/java/CustomConverterDemo.java`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class CustomConverterDemo {

    private record OrderCommand(String orderId, int quantity) {
        OrderCommand {
            if (orderId == null || orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order command");
            }
        }
    }

    private static final class OrderCommandConverter
            extends AbstractMessageConverter {

        OrderCommandConverter() {
            super(MimeTypeUtils.TEXT_PLAIN);
            setStrictContentTypeMatch(true);
        }

        @Override
        protected boolean supports(Class<?> clazz) {
            return OrderCommand.class == clazz;
        }

        @Override
        protected Object convertToInternal(
                Object payload,
                MessageHeaders headers,
                Object conversionHint) {

            OrderCommand command = (OrderCommand) payload;
            return command.orderId() + "|" + command.quantity();
        }

        @Override
        protected Object convertFromInternal(
                Message<?> message,
                Class<?> targetClass,
                Object conversionHint) {

            String[] fields = ((String) message.getPayload())
                    .split("\\|", -1);

            if (fields.length != 2) {
                throw new IllegalArgumentException(
                        "Invalid OrderCommand wire payload");
            }

            return new OrderCommand(
                    fields[0],
                    Integer.parseInt(fields[1]));
        }
    }

    public static void main(String[] args) {
        OrderCommandConverter converter = new OrderCommandConverter();

        OrderCommand source = new OrderCommand("ORD-42", 3);

        // Provide a matching contentType because the converter enables strict matching.
        MessageHeaders textHeaders = MessageBuilder
                .withPayload("header-template")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN)
                .build()
                .getHeaders();

        Message<?> wire = converter.toMessage(source, textHeaders);

        OrderCommand restored = (OrderCommand) converter.fromMessage(
                wire, OrderCommand.class);

        // String payload is not supported.
        Message<?> unsupportedSource = converter.toMessage(
                "plain text", textHeaders);

        // Target type Integer is not supported.
        Object unsupportedTarget = converter.fromMessage(
                wire, Integer.class);

        // MIME type application/json is not accepted.
        Message<String> wrongMime = MessageBuilder
                .withPayload("ORD-42|3")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .build();

        Object rejectedMime = converter.fromMessage(
                wrongMime, OrderCommand.class);

        // Valid content type, but payload does not match the wire format.
        Message<String> malformedWire = MessageBuilder
                .withPayload("ORD-42|not-a-number")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN)
                .build();

        boolean malformedRejected;
        try {
            converter.fromMessage(malformedWire, OrderCommand.class);
            malformedRejected = false;
        }
        catch (IllegalArgumentException ex) {
            malformedRejected = true;
        }

        System.out.println("wire payload: " + wire.getPayload());
        System.out.println("wire contentType: "
                + wire.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("restored: " + restored.orderId()
                + ", quantity=" + restored.quantity());
        System.out.println("unsupported source returns null: "
                + (unsupportedSource == null));
        System.out.println("unsupported target returns null: "
                + (unsupportedTarget == null));
        System.out.println("unsupported contentType returns null: "
                + (rejectedMime == null));
        System.out.println("malformed payload rejected: "
                + malformedRejected);
    }
}
```

Create `pom.xml` at the root directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>custom-message-converter-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>CustomConverterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Run from the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Stdout output:

```text
wire payload: ORD-42|3
wire contentType: text/plain
restored: ORD-42, quantity=3
unsupported source returns null: true
unsupported target returns null: true
unsupported contentType returns null: true
malformed payload rejected: true
```

The example demonstrates three independent support conditions working together:

1. The input payload must be `OrderCommand`.
2. The target type when reading must be `OrderCommand`.
3. The content type must be compatible with `text/plain` declared by the converter.

When all conditions are met but the content is invalid, the converter throws an error to inform the caller that the data is malformed.

## 6. Registering the Converter with a Template

When using the conversion methods on a messaging template, you can attach a custom converter using `setMessageConverter`:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setMessageConverter(new OrderCommandConverter());
```

The template uses the configured converter for payload conversion operations such as `convertAndSend` and `convertSendAndReceive`. When using request-reply, the converter must support both the outbound request type and the reply type the caller wants to receive.

For `convertSendAndReceive`, the general flow is:

1. The converter transforms the request payload into a message.
2. The template sends the request and waits for a reply.
3. The converter converts the reply message into the target type requested by the caller.

If the converter only supports `OrderCommand` while the reply is `OrderReply`, extend the converter to support both types or use another appropriate converter. Do not assume a converter only needs to support the outbound direction.

## 7. SmartMessageConverter and Conversion Hints

`SmartMessageConverter` extends `MessageConverter` with two overloads taking an extra `conversionHint`:

```java
Message<?> toMessage(
        Object payload,
        MessageHeaders headers,
        Object conversionHint);

Object fromMessage(
        Message<?> message,
        Class<?> targetClass,
        Object conversionHint);
```

A hint is metadata for the conversion process, such as generic type information or annotations passed by the framework. It does not replace payload type or content type.

`AbstractMessageConverter` already implements `SmartMessageConverter`. If a converter does not need hints, it can ignore this parameter as in the example. If needed, override the hooks taking `conversionHint` to customize serialization/deserialization based on context.

Do not stuff arbitrary business data into conversion hints. Use headers for message metadata; use hints for conversion-control information supplied by the caller/framework.

## 8. CompositeMessageConverter and Converter Ordering

When an application supports multiple data types, you can use `CompositeMessageConverter` to combine multiple converters:

```java
MessageConverter composite = new CompositeMessageConverter(
        List.of(
                new OrderCommandConverter(),
                new ByteArrayMessageConverter(),
                new StringMessageConverter()
        )
);
```

The composite tries converters in the provided list order and uses the first successful conversion result. Therefore, order matters greatly:

- Place specialized converters before general converters.
- Do not let an overly broad converter accept payloads it does not truly understand.
- Each converter must return `null` when unsupported so the composite can try the next converter.
- When data falls within the converter's scope but is malformed, throw a clear exception so errors are not masked by another converter.

When combining JSON, string, and byte-array converters, define MIME types and Java types clearly to avoid two converters accepting the same message in different ways.

## 9. Rules for Designing a Custom Converter

### Check both type and content type

A converter should only accept a message when:

- The payload or target class is within its declared set of supported types.
- The content type is compatible with formats the converter supports.
- The payload has valid structure per the converter's schema/wire format.

Do not check only the class name and assume every payload is structurally valid.

### Do not hide invalid data

Returning `null` when a converter does not support a message is appropriate. However, once a converter accepts a message and detects a malformed payload, throw an exception with a specific cause, for example:

- Missing required field.
- Unparseable number.
- Unsupported schema version.
- Invalid JSON/XML/byte sequence.
- Data exceeding size limits.

### Keep content type accurate

Set `contentType` to match the wire format. If the converter serializes JSON, use a JSON MIME type; if it serializes plain text, use `text/plain`. Do not use content type solely to force a particular converter to be selected.

### Handle null and data types

Specify clearly whether the converter accepts null payloads. For critical DTOs, validate required fields and value ranges during deserialization or in the DTO constructor.

### Versioning and backward compatibility

When a wire format changes, consider:

- Adding a schema version or versioned content type.
- Maintaining the ability to read older message versions during migration windows.
- Never changing the meaning of existing fields without bumping the version.
- Writing tests for both current and historical data.

## 10. Testing Support Conditions

A useful test suite should cover at least these cases:

| Case | Expected outcome |
| --- | --- |
| Payload matches class, content type matches | Message created successfully |
| Message matches wire format, target class matches | DTO restored successfully |
| Unsupported payload class | Converter returns `null` |
| Unsupported target class | Converter returns `null` |
| Unsupported content type with strict match | Converter declines message |
| Missing content type with strict match | Converter declines message |
| Valid content type but corrupted payload | Throws conversion error |
| Payload with boundary values or missing fields | Follows defined validation |
| Multiple converters present | Specialized converter tried before general converter |

Beyond unit tests, add integration tests at real transport boundaries. A converter working well with `MessageBuilder` does not prove a broker, WebSocket adapter, or JMS provider is sending the right content type and encoding.

## 11. Common Mistakes

1. **Overriding only `convertToInternal` and forgetting `convertFromInternal`.** The converter works in only one direction.
2. **`supports` returning true for every class.** The converter may accept data it cannot serialize or deserialize.
3. **Declaring wrong or overly broad MIME types.** The converter may accept messages in the wrong format.
4. **Enabling strict matching without attaching content type.** The converter rejects messages even when the payload class is right.
5. **Returning `null` on malformed payloads.** Data errors get mistaken for an unsupported converter.
6. **Failing to check target class on deserialization.** Can return an object of a type the caller did not request.
7. **Placing general converters before specialized converters.** The composite may pick the wrong converter.
8. **Forgetting to register the converter on the template.** Code calling `convertAndSend` still uses the default converter.
9. **Not testing both directions.** The producer can serialize, but the consumer cannot deserialize the same wire format.
10. **Not versioning schemas.** Format changes can break in-flight messages or make producer/consumer versions incompatible.

## 12. Implementation Checklist

- Choose whether to implement `MessageConverter` directly or extend `AbstractMessageConverter`.
- Explicitly list supported classes in `supports(Class<?>)`.
- Declare accurate MIME types.
- Decide whether to enable `strictContentTypeMatch`.
- Implement both Java-to-message and message-to-Java directions.
- Return `null` when unsupported; throw an error when data is in scope but malformed.
- Validate content type, encoding, schema, and size limits.
- Register the converter on the appropriate template or composite converter.
- Place specialized converters before general converters.
- Test unsupported types, unsupported MIME types, malformed payloads, round-trips, and version compatibility.

## 13. References

- [Spring Framework – MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework – AbstractMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/AbstractMessageConverter.html)
- [Spring Framework – SmartMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/SmartMessageConverter.html)
- [Spring Framework – CompositeMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/CompositeMessageConverter.html)
- [Spring Framework – MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
