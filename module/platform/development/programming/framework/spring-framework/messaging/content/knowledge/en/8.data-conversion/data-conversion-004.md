# CompositeMessageConverter and Converter Selection Order

## Objectives

After this lesson, you will be able to:

- Explain the roles of `MessageConverter`, `SmartMessageConverter`, and `CompositeMessageConverter`.
- Describe how a composite tries each converter in turn and stops at the first non-`null` result.
- Distinguish the application-supplied ordering in `CompositeMessageConverter` from Spring Integration `ConfigurableCompositeMessageConverter`'s default ordering.
- Understand how `MessageHeaders.CONTENT_TYPE`, payload type, and target type affect converter selection.
- Choose the right position for custom converters and prevent overly broad converters from shadowing specialized ones.
- Write a Java 17 example testing both deserialization and serialization directions.

## 1. What Problem Does MessageConverter Solve?

A Spring `Message<T>` consists of a payload and headers. When a message travels through an endpoint or transport, the actual data type of the payload may differ from the type expected by the handler.

Examples:

- A producer receives a JSON document from an external system as a `byte[]`.
- A business handler expects an `Order` Java object.
- When sending outbound, the `Order` object must be converted to JSON bytes.
- A text message may need conversion from `String` to `Integer` for a handler parameter.

`MessageConverter` is the abstraction for converting payloads between a serialized form and a target Java type. It operates on messages and can inspect the `MessageHeaders.CONTENT_TYPE` header to determine the data's MIME type.

The two conversion directions:

~~~text
Inbound:
Message<byte[]> + Content-Type: application/json
              |
              v
       MessageConverter
              |
              v
            Order

Outbound:
          Order
              |
              v
       MessageConverter
              |
              v
Message<byte[]> + Content-Type: application/json
~~~

Distinguish `MessageConverter` from `org.springframework.core.convert.converter.Converter`:

- `MessageConverter` converts payloads in a message context, typically based on MIME type and target type.
- `Converter<S, T>` and `ConversionService` convert between Java types, such as `String` to `Integer`.
- `GenericMessageConverter` bridges both mechanisms by using `ConversionService` to convert payloads when possible.

## 2. How Does CompositeMessageConverter Work?

`org.springframework.messaging.converter.CompositeMessageConverter` is a `MessageConverter` that wraps a collection of other converters. It tries each converter in collection order until one returns a non-`null` result.

This mechanism applies to both:

- `fromMessage(message, targetClass)`: converts a message payload to the target Java type.
- `toMessage(payload, headers)`: converts an object to a serialized payload and creates a new message.

You can visualize the algorithm:

~~~text
Start
  |
  v
Converter #1
  |
  +-- returns non-null result --> Stop, use result
  |
  +-- returns null
          |
          v
     Converter #2
          |
          +-- returns non-null result --> Stop, use result
          |
          +-- returns null
                  |
                  v
             Next converter
                  |
                  v
        End of list, still null
                  |
                  v
          Composite returns null
~~~

The key rule is **first non-null wins**:

1. The composite does not run every converter and pick the best result.
2. The composite does not automatically sort by MIME type or specificity.
3. Whichever converter appears first and handles the message ends the selection.
4. A converter that does not support the MIME type, payload, or target type should return `null`.
5. If no converter can handle it, the composite returns `null`; the calling endpoint may turn that situation into a conversion error.
6. If a converter accepted the message for handling but the data is invalid, the converter may throw `MessageConversionException`. Exceptions should not be used as a signal to try the next converter.

Therefore, collection ordering is part of behavioral configuration, not a presentation detail.

### CompositeMessageConverter has no built-in default converter list

Spring Framework's constructor takes a collection supplied by the application:

~~~java
List<MessageConverter> converters = List.of(
        jsonConverter,
        byteArrayConverter,
        stringConverter
);

CompositeMessageConverter composite =
        new CompositeMessageConverter(converters);
~~~

The order in the list above is the order the composite will try. If you want deterministic ordering, use an ordered `List` such as `List.of(...)` or `ArrayList`; avoid relying on the unspecified order of a collection like `HashSet`.

`CompositeMessageConverter` also implements `SmartMessageConverter`. When the caller passes a conversion hint, the composite forwards that hint to delegates that also implement `SmartMessageConverter`. The hint can carry context such as `MethodParameter` or parameter/method metadata.

## 3. Factors Determining Whether a Converter Can Handle a Message

A converter typically evaluates several factors at once:

| Factor | Meaning |
|---|---|
| Payload type | Current object type, e.g. `byte[]`, `String`, or `Order` |
| Target type | Java type that `fromMessage` needs to produce |
| Content type | MIME type in the `MessageHeaders.CONTENT_TYPE` header, e.g. `application/json` |
| Conversion direction | Reading serialized payload into an object vs. serializing an object into a message |
| Conversion hint | Additional context for `SmartMessageConverter` |

For inbound conversion, the `contentType` header specifies the payload's MIME type. For outbound conversion, the `headers` argument to `toMessage` can carry the desired MIME type.

Example:

~~~java
Message<byte[]> message = MessageBuilder
        .withPayload(jsonBytes)
        .setHeader(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
        )
        .build();

Order order = (Order) converter.fromMessage(message, Order.class);
~~~

If the payload is JSON but the header declares `text/plain`, the JSON converter may decline to handle it and return `null`. A text converter or another converter further down the list might then be tried. Setting the right content type is the responsibility of the producer or adapter creating the message.

Do not guess format by looking only at the payload. A string could be plain text, JSON, XML, or content of a custom protocol. Content type lets the consumer interpret the payload according to an agreed contract.

## 4. Spring Integration's Default Ordering

Distinguish the Spring Framework class from Spring Integration's extension:

- `CompositeMessageConverter` belongs to Spring Framework's Spring Messaging module. It uses the exact collection passed to its constructor.
- `ConfigurableCompositeMessageConverter` belongs to Spring Integration and extends `CompositeMessageConverter`. It provides a default list of converters for content-type conversion at message endpoints.

When Jackson is on the classpath, Spring Integration's default list is declared in this order:

| Order | Converter | Primary role |
|---:|---|---|
| 1 | `MappingJackson2MessageConverter` | Converts JSON and Java objects; present only when Jackson processor is on the classpath |
| 2 | `ByteArrayMessageConverter` | Converts `byte[]` payloads with MIME type `application/octet-stream` |
| 3 | `ObjectStringMessageConverter` | Converts Strings and can convert other objects to String via `toString()` |
| 4 | `GenericMessageConverter` | Uses `ConversionService` to convert Java types when a matching converter exists |

If Jackson is not on the classpath, the first JSON converter is not registered; the remaining default converters keep their corresponding order.

`ObjectStringMessageConverter` is a Spring Integration converter, not a default converter of plain Spring Framework. It serves as a fallback converting objects to String. Documentation recommends using its `fromMessage` direction with target type `String.class`; do not use `toString()` as a JSON serialization mechanism or a data transport contract.

### Constructors of ConfigurableCompositeMessageConverter

Spring Integration provides three ways to construct it:

~~~java
// Default converter list.
new ConfigurableCompositeMessageConverter();

// Use only custom converters; do not add defaults.
new ConfigurableCompositeMessageConverter(customConverters);

// Custom converters first, default converters appended at the end.
new ConfigurableCompositeMessageConverter(customConverters, true);
~~~

The third approach is useful when the application needs to prioritize custom formats while still keeping standard fallbacks. Custom converters must return `null` when they do not support a message so the composite continues trying subsequent converters.

## 5. Why Does Order Matter?

Suppose an application has:

- A converter specialized for JSON.
- A converter specialized for bytes.
- A converter that can convert many types into String.
- A general converter using `ConversionService`.

Specialized converters should generally precede broad fallback converters. If a broad converter appears too early and returns a result for a payload that a specialized converter handles better, the composite stops immediately at that result.

Some scenarios:

**JSON bytes to Order**

- `MappingJackson2MessageConverter` checks content type `application/json` and target type `Order`.
- If supported, it returns `Order`.
- The composite stops; byte-array, string, and generic converters are not invoked.

**Binary bytes to byte[]**

- The JSON converter does not support `application/octet-stream`, so it returns `null`.
- `ByteArrayMessageConverter` handles the payload.
- The composite stops at the second converter.

**Text to String**

- The JSON and byte-array converters do not support the corresponding MIME/payload/target combination.
- `StringMessageConverter` or `ObjectStringMessageConverter` can handle it depending on the active list.

**String to Integer**

- The text converter may not support target type `Integer`.
- `GenericMessageConverter` tries `ConversionService`.
- If `ConversionService` can convert `String` to `Integer`, the result is returned.

Do not place a converter that handles every payload at the front of the list just because it is “flexible”. An overly broad fallback can shadow format-specific converters and change results when dependencies are added or content types change.

## 6. Java 17 Example: Trying Converters in Order

This example uses Spring Framework 6.2.18, Java 17, and Jackson 2.18.3. It builds a `CompositeMessageConverter` with four delegates in an explicit order, then tests JSON, bytes, text, and Java type conversion.

Directory structure:

~~~text
composite-message-converter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CompositeConverterDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>composite-message-converter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
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

File `src/main/java/demo/CompositeConverterDemo.java`:

~~~java
package demo;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.ByteArrayMessageConverter;
import org.springframework.messaging.converter.CompositeMessageConverter;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class CompositeConverterDemo {

    public static void main(String[] args) {
        List<MessageConverter> delegates = List.of(
                new MappingJackson2MessageConverter(),
                new ByteArrayMessageConverter(),
                new StringMessageConverter(),
                new GenericMessageConverter()
        );

        CompositeMessageConverter composite =
                new CompositeMessageConverter(delegates);

        String order = delegates.stream()
                .map(converter -> converter.getClass().getSimpleName())
                .collect(Collectors.joining(" -> "));

        System.out.println("converterOrder=" + order);

        String json = """
                {"orderId":"ORD-1001","total":125.00}
                """.trim();

        Message<byte[]> jsonMessage = MessageBuilder
                .withPayload(json.getBytes(StandardCharsets.UTF_8))
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON
                )
                .build();

        Order convertedOrder = (Order) composite.fromMessage(
                jsonMessage,
                Order.class
        );

        System.out.println(
                "jsonOrder=" + convertedOrder.orderId()
                        + ":" + convertedOrder.total().toPlainString()
        );

        Message<?> outbound = composite.toMessage(convertedOrder, null);

        System.out.println(
                "outboundPayloadType="
                        + outbound.getPayload().getClass().getSimpleName()
        );
        System.out.println(
                "outboundContentTypePresent="
                        + (outbound.getHeaders().get(
                                MessageHeaders.CONTENT_TYPE) != null)
        );

        Message<byte[]> binaryMessage = MessageBuilder
                .withPayload("raw".getBytes(StandardCharsets.UTF_8))
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_OCTET_STREAM
                )
                .build();

        byte[] binary = (byte[]) composite.fromMessage(
                binaryMessage,
                byte[].class
        );

        System.out.println("rawByteCount=" + binary.length);

        Message<String> textMessage = MessageBuilder
                .withPayload("hello")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN
                )
                .build();

        String text = (String) composite.fromMessage(
                textMessage,
                String.class
        );

        System.out.println("plainText=" + text);

        Message<String> numberMessage = MessageBuilder
                .withPayload("42")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN
                )
                .build();

        Integer number = (Integer) composite.fromMessage(
                numberMessage,
                Integer.class
        );

        System.out.println("genericInteger=" + number);
    }
}

record Order(String orderId, BigDecimal total) {}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.CompositeConverterDemo
~~~

Stdout output:

~~~text
converterOrder=MappingJackson2MessageConverter -> ByteArrayMessageConverter -> StringMessageConverter -> GenericMessageConverter
jsonOrder=ORD-1001:125.00
outboundPayloadType=byte[]
outboundContentTypePresent=true
rawByteCount=3
plainText=hello
genericInteger=42
~~~

Explanation:

- JSON bytes have content type `application/json`, so the Jackson converter produces `Order`.
- When serializing `Order`, the Jackson converter creates a message with a byte payload and the default JSON content type.
- The binary message uses `application/octet-stream`, so the byte-array converter handles it.
- The text message uses `text/plain`, so the string converter handles it.
- With target `Integer`, the string converter does not match the target type; the generic converter uses `ConversionService` to convert `"42"` to `42`.
- The list passed to the constructor defines the exact priority order. The composite stops as soon as a converter returns a non-`null` result.

## 7. Registering Custom Converters in Spring Integration

Spring Integration uses `ConfigurableCompositeMessageConverter` in message endpoint argument resolution. Conversion can rely on the `contentType` header when an endpoint needs to convert the payload into a handler parameter type.

You can customize the default converter chain via a bean named specifically for the argument resolver:

~~~java
@Configuration(proxyBeanMethods = false)
public class MessageConversionConfiguration {

    @Bean(
        name = IntegrationContextUtils
                .ARGUMENT_RESOLVER_MESSAGE_CONVERTER_BEAN_NAME
    )
    public ConfigurableCompositeMessageConverter argumentResolverConverter(
            MessageConverter xmlConverter,
            MessageConverter protobufConverter) {

        return new ConfigurableCompositeMessageConverter(
                List.of(xmlConverter, protobufConverter),
                true
        );
    }
}
~~~

In the configuration above:

1. `xmlConverter` is tried first.
2. `protobufConverter` is tried next.
3. Spring Integration's default converters are appended at the end because `registerDefaults` is `true`.
4. Custom converters must return `null` when they do not support a message so subsequent converters have a chance to process it.

If you want to use only custom converters and drop all defaults, use the constructor taking a collection without passing `registerDefaults = true`:

~~~java
new ConfigurableCompositeMessageConverter(
        List.of(xmlConverter, protobufConverter)
);
~~~

The no-arg constructor builds the default list. The constructor taking only a collection creates a custom-only list. The constructor taking a collection and `true` places custom converters before defaults. Choose explicitly according to your intent so you do not accidentally omit standard converters.

If the application needs to replace the entire argument resolution conversion mechanism, Spring Integration also allows registering a standalone `MessageConverter` under the bean name `integrationArgumentResolverMessageConverter`. In that case, the application assumes responsibility for the entire conversion policy.

## 8. MessageConverter and ConversionService in Spring Integration

Two mechanisms are often confused because both perform data conversion:

| Mechanism | Input and output | When to use |
|---|---|---|
| `MessageConverter` | Serialized message payload ↔ Java object | Converting JSON bytes to a DTO, or a DTO to bytes |
| `ConversionService` | One Java type ↔ another Java type | Converting String to Integer, enum, number, or application type |
| `GenericMessageConverter` | Message payload ↔ target type via ConversionService | Used in a composite when specialized converters do not handle it |

Spring Integration also has `integrationConversionService` for type conversions within Integration's runtime, such as payload type conversion and data type channels. It differs from `ConfigurableCompositeMessageConverter`, which is used for content-type conversion when invoking endpoint methods.

Do not register converters for Spring constructor/property binding and assume they will automatically be used for runtime message conversion. Share a `ConversionService` only when an alias or intentional wiring has been configured.

## 9. Common Mistakes

1. **Assuming CompositeMessageConverter has built-in default converters.** Spring Framework's composite only uses the collection passed to its constructor. The default list belongs to Spring Integration's `ConfigurableCompositeMessageConverter`.
2. **Confusing list order with best MIME-type order.** The composite tries converters in collection order; it does not rank them by specificity.
3. **Using a collection without stable ordering.** Use a `List` so converter selection results are predictable.
4. **Placing a broad fallback before specialized converters.** A converter that returns a result early will block converters behind it.
5. **Using ObjectStringMessageConverter to serialize JSON.** It may call `toString()`; that output is not a JSON contract.
6. **Missing or misdeclared content type.** A converter may return `null` even if the payload appears to be in the right format.
7. **Confusing null with an exception.** `null` means the converter cannot handle it and the composite tries the next one. An exception normally signals a failure after a converter accepted the message but the data or configuration is invalid.
8. **Accidentally dropping default converters.** `ConfigurableCompositeMessageConverter`'s collection-only constructor does not add defaults automatically; to retain defaults after custom converters, use the constructor with `registerDefaults = true`.
9. **Testing only inbound.** Test both `fromMessage` and `toMessage`, as a converter may support one direction without supporting the other.
10. **Confusing MessageConverter with HTTP MessageConverter.** `org.springframework.messaging.converter.MessageConverter` is the abstraction for Spring Messaging; `org.springframework.http.converter.HttpMessageConverter` belongs to Spring Web and has a different contract.
11. **Assuming GenericMessageConverter can convert any type.** It converts only when `ConversionService` finds a suitable converter.
12. **Deserializing external data without controlling the target type.** Specify target types explicitly, manage Jackson configuration, and do not trust type metadata supplied by untrusted sources.

## 10. Converter Chain Design Checklist

- [ ] Identify the conversion direction: serialized payload to object, or object to serialized payload.
- [ ] Identify payload type, target type, and content type for each message kind.
- [ ] Use `CompositeMessageConverter` with a clearly ordered `List`.
- [ ] Place specialized converters before broad fallback converters.
- [ ] Ensure converters return `null` when they do not support a message.
- [ ] Let invalid data errors be represented by appropriate exceptions.
- [ ] Distinguish Spring Framework's composite from Spring Integration's configurable composite.
- [ ] Decide whether to keep default converters or replace the entire list.
- [ ] Verify the Jackson dependency if the default JSON converter is needed.
- [ ] Set `MessageHeaders.CONTENT_TYPE` accurately for the payload format.
- [ ] Test delegate ordering, both inbound and outbound, as well as the case where no converter matches.
- [ ] Monitor conversion failures and log enough metadata to identify content type, target type, and the selected converter.

## 11. Conclusion

`CompositeMessageConverter` is a chain of `MessageConverter`s tried in the exact order registered; the first converter returning a non-`null` result is selected. Spring Framework provides the general-purpose composite, while Spring Integration provides `ConfigurableCompositeMessageConverter` with a documented default list comprising Jackson, byte array, object-to-string, and generic conversion in that order. To ensure the right converter is chosen, control list order, content type, payload type, and target type; place specialized converters before fallbacks and test both conversion directions.

## Official References

- [Spring Framework 6.2.18 Javadoc: CompositeMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/CompositeMessageConverter.html) — first-non-null delegation, constructor, fromMessage, toMessage, and conversion hints.
- [Spring Framework 6.2.18 Javadoc: MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/MessageConverter.html) — payload conversion contract and content type usage.
- [Spring Framework 6.2.18 Javadoc: MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html) — JSON conversion with Jackson.
- [Spring Framework 6.2.18 Javadoc: ByteArrayMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/ByteArrayMessageConverter.html) — support for application/octet-stream and byte[].
- [Spring Framework 6.2.18 Javadoc: GenericMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html) — using ConversionService for Java type conversion.
- [Spring Integration 6.5 Reference: Message Endpoints — Content Type Conversion](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html) — default ordering of ConfigurableCompositeMessageConverter and how to register custom converters.
- [Spring Integration 6.1 Javadoc: ConfigurableCompositeMessageConverter](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/support/converter/ConfigurableCompositeMessageConverter.html) — constructors and defaults/custom converters ordering.
- [Spring Integration 6.1 Javadoc: ObjectStringMessageConverter](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/support/converter/ObjectStringMessageConverter.html) — object-to-String conversion behavior and recommended scope.
- [Spring Framework 6.2 Reference: Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html) — ConversionService and conversion mechanisms between Java types.
