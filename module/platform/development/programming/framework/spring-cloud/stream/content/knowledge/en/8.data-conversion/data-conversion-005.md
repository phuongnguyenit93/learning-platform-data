# MessageConverter Selection Mechanism and Registering Custom Converters

Spring Cloud Stream needs to convert payloads between the broker's data representation and the Java types used by functions. This conversion mechanism is carried out through Spring Messaging's `MessageConverter` implementations. A suitable converter is chosen based on the content type (MIME type/content type), the target type or payload type, and the converter's supported capabilities.

When the application's standard message format is not fully supported by default converters, a custom converter can be registered. This should be done deliberately: define the content type, supported Java types, bidirectional conversion logic, and how invalid data is handled. You should also distinguish Spring Cloud Stream's message conversion from native serialization/deserialization performed by the binder and broker.

## 1. What Does MessageConverter Do?

A message in Spring Messaging consists of a payload and headers. The payload may be a Java object, a string, or a byte array; headers carry metadata such as content type, ID, and correlation ID.

`MessageConverter` converts payloads between the message representation and the Java type needed by the application. The two primary operations are:

- **Inbound conversion**: converting a payload received from a binding into the function's parameter type, such as a JSON byte array into `OrderCreated`.
- **Outbound conversion**: converting a Java object returned by a function into a payload format suitable for transmission over the broker, such as `OrderAccepted` into JSON bytes.

Overall flow:

```mermaid
flowchart LR
    A[Broker record / message] --> B[Binder receives data]
    B --> C[Content type + target Java type]
    C --> D[Matching MessageConverter]
    D --> E[Function with Java payload]
    E --> F[Function returns payload]
    F --> G[Outbound MessageConverter]
    G --> H[Binder sends data]
    H --> I[Broker]
```

This is the logical model of the message processing path. Depending on the binder and native encoding/decoding settings, some conversion steps may be handled by the broker's serializer/deserializer instead of a Spring Cloud Stream converter.

## 2. How Content Type Participates in Selecting a Converter

Content type describes the format of a payload. Some common values:

| Content type | Common payload format | Example |
|---|---|---|
| `application/json` | JSON | `{"orderId":"o-1"}` |
| `text/plain` | Plain text | `order-created` |
| `text/csv` | CSV data | `o-1,c-1,125000` |
| `application/octet-stream` | Binary data | byte array |
| `application/avro` | Avro data | Avro binary or configured format |
| `application/x-protobuf` | Protocol Buffers data | Protobuf binary |

In Spring Cloud Stream, the content type can be determined from the message's `contentType` header, the binding's `content-type` property, or the framework's default value. A message header can override binding configuration. If unspecified, Spring Cloud Stream generally uses `application/json` as the default for message conversion. Check the exact framework and binder version in use when relying on this precedence order.

Example configuring content type for a binding:

```yaml
spring:
  cloud:
    function:
      definition: receiveOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: orders.created
          group: order-service
          content-type: application/json
```

The binding declares that the payload is handled as JSON. When the function accepts a specific Java type, the JSON converter can decode the payload into that type:

```java
@Bean
Consumer<OrderCreated> receiveOrder(OrderService service) {
    return service::handle;
}
```

In the example, Spring Cloud Stream uses the `OrderCreated` parameter type as the target type for inbound conversion. If the function accepts `Message<OrderCreated>`, the converter can still convert the payload while preserving appropriate message headers.

Do not confuse content type with schema version. `application/json` only indicates JSON format; it does not state which contract version the JSON conforms to. Schema versions must be managed in an envelope, agreed metadata, or a schema registry.

## 3. How the Framework Selects a MessageConverter

Spring Messaging provides a mechanism to select converters based on content type and data type support. In Spring Cloud Stream, default converters and custom converters are placed in the conversion chain so the framework can find a suitable match.

The selection flow can be pictured as follows:

1. Determine content type from the message header or binding configuration.
2. Determine the Java type to receive or the payload type to send.
3. Find a converter that supports that content type and can convert the corresponding data type.
4. Perform inbound or outbound conversion.
5. If no suitable converter exists or the data cannot be converted, processing raises a conversion error.

Supporting a MIME type alone does not guarantee a converter can convert every Java type. A converter may also restrict which classes it handles. For example, a CSV converter may support `text/csv` yet only convert `OrderCreated`; it should not accept arbitrary objects and try to parse them using an undefined CSV structure.

Common default converters typically support JSON, String, and byte arrays. The exact converter set depends on the Spring Framework/Spring Cloud Stream version, classpath, and application configuration. Therefore, specify payload types and content types explicitly rather than relying on implicit conversion.

### JSON

With `application/json`, the JSON converter typically uses Jackson to convert Java objects to JSON and back. Example payload:

```json
{
  "orderId": "order-1007",
  "customerId": "customer-42",
  "total": 125000
}
```

This can be mapped into a record:

```java
public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {}
```

Data types, field names, constructors, and Jackson configuration must be compatible with the actual JSON. If the JSON lacks required fields or contains unparseable values, conversion may fail.

### String and byte array

With `text/plain`, the String converter typically handles text. With `application/octet-stream`, the payload is typically kept as `byte[]`. If the application needs to decode binary data itself, you can declare a function accepting `byte[]` or `Message<byte[]>` and invoke a specialized library in the adapter.

Example receiving raw data:

```java
@Bean
Consumer<byte[]> receiveRawPayload(RawPayloadService service) {
    return service::process;
}
```

This approach is useful when the application needs full control over the format or uses a custom decoding library. However, handling byte arrays directly means the application must manage format checks, charset, parse errors, and payload size limits.

## 4. Choosing the Right Function Parameter Type

The function's parameter type directly affects the conversion target type:

| Function signature | Expected outcome |
|---|---|
| `Consumer<OrderCreated>` | Payload is converted into `OrderCreated` |
| `Function<OrderCreated, OrderAccepted>` | Input payload becomes `OrderCreated`; output result is converted according to the output binding's content type |
| `Consumer<Message<OrderCreated>>` | Receives the message envelope and the payload converted into `OrderCreated` |
| `Consumer<byte[]>` | Receives raw binary payload for application-level handling |
| `Function<String, String>` | Converts payload to String before calling the function |

Use a concrete Java type when you want the framework to perform conversion. Use `Message<T>` when you need to read headers. Use `byte[]` when you want to process raw data or use a custom decoder.

Example of a function reading a message and returning a new message:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderService service) {

    return input -> {
        OrderAccepted result = service.accept(input.getPayload());

        return MessageBuilder
            .withPayload(result)
            .setHeader("correlationId",
                input.getHeaders().get("correlationId"))
            .build();
    };
}
```

The output binding's content type must match a converter capable of converting `OrderAccepted` to the target format. Headers kept or forwarded must follow the binder's rules; do not assume every internal header is transmitted intact through the broker.

## 5. When Is a Custom Converter Needed?

Default converters are usually sufficient for JSON, String, and byte arrays. A custom converter is suitable when the application uses specialized formats or mapping rules, for example:

- The payload is CSV following a fixed contract.
- A legacy system uses a custom text format.
- A binary type must be decoded using a specialized library.
- Mapping rules between payload and Java objects differ from default JSON rules.
- The application needs to support a custom MIME type agreed upon with producers/consumers.

Before writing a converter, consider whether a binder serializer/deserializer, format library, or schema registry is a better fit. If the format is Avro or Protobuf and the binder already has native serializer/deserializer integration, using that mechanism may be cleaner than writing a general `MessageConverter`.

A custom converter should have a narrow scope: support specific MIME types, specific Java types, and clearly define behavior in both inbound and outbound directions. Do not register an overly broad converter that could compete with the default JSON converter.

## 6. Implementing a Custom Converter for CSV Format

Suppose a legacy system emits order events as CSV with three fields:

```text
order-1007,customer-42,125000
```

The application wants to convert this data into a record:

```java
public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {}
```

You can create a converter by extending `AbstractMessageConverter`. This class supports declaring MIME types and inbound/outbound conversion hooks:

```java
public class OrderCsvMessageConverter extends AbstractMessageConverter {

    public OrderCsvMessageConverter() {
        super(MimeTypeUtils.parseMimeType("text/csv"));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return OrderCreated.class.isAssignableFrom(clazz);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message,
            Class<?> targetClass,
            Object conversionHint) {

        String csv = payloadAsString(message.getPayload());
        String[] fields = csv.split(",", -1);

        if (fields.length != 3) {
            throw new MessageConversionException(
                message, "Expected 3 CSV fields"
            );
        }

        try {
            return new OrderCreated(
                fields[0].trim(),
                fields[1].trim(),
                new BigDecimal(fields[2].trim())
            );
        } catch (RuntimeException ex) {
            throw new MessageConversionException(
                message, "Invalid OrderCreated CSV payload", ex
            );
        }
    }

    @Override
    protected Object convertToInternal(
            Object payload,
            MessageHeaders headers,
            Object conversionHint) {

        if (!(payload instanceof OrderCreated event)) {
            return null;
        }

        return String.join(
            ",",
            event.orderId(),
            event.customerId(),
            event.total().toPlainString()
        );
    }

    private String payloadAsString(Object payload) {
        if (payload instanceof byte[] bytes) {
            return new String(bytes, StandardCharsets.UTF_8);
        }
        if (payload instanceof String text) {
            return text;
        }
        throw new IllegalArgumentException(
            "CSV payload must be String or byte[]"
        );
    }
}
```

The converter above supports the `text/csv` MIME type and the `OrderCreated` Java type. On receive, it accepts String or UTF-8 byte array payloads, validates field count, and parses the total amount. On send, it converts `OrderCreated` into a CSV string.

This is a simple CSV example assuming values do not contain commas, newlines, or quotes requiring escaping. For production CSV with quoting/escaping rules, use a dedicated CSV library instead of `String.split()`. You should also bound payload size and validate individual field values before business processing.

A production converter should throw `MessageConversionException` when a payload has the matching MIME type but malformed structure. When a converter does not support the payload type or MIME type, it should let other converters handle it by declining that conversion.

## 7. Registering the Converter with Spring Cloud Stream

Spring Cloud Stream allows registering a custom converter via a bean annotated with `@StreamMessageConverter`. This annotation lets the framework recognize the bean as a converter for Spring Cloud Stream message conversion.

```java
@Configuration
public class MessageConversionConfiguration {

    @Bean
    @StreamMessageConverter
    public MessageConverter orderCsvMessageConverter() {
        return new OrderCsvMessageConverter();
    }
}
```

The converter is added to Spring Cloud Stream's conversion mechanism. You do not need to manually create a `MessageChannel` or invoke the converter directly inside each function when the framework can determine the content type and target type.

After registering the converter, configure the binding to use the matching MIME type:

```yaml
spring:
  cloud:
    function:
      definition: receiveOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: legacy.orders
          group: order-service
          content-type: text/csv
```

The function can receive the converted payload:

```java
@Bean
Consumer<OrderCreated> receiveOrder(OrderService service) {
    return service::handle;
}
```

If a producer sends a CSV payload, the binder receives the message and the converter is selected based on `text/csv` and the target type `OrderCreated`. On the output side, the output binding also needs the corresponding content type if you want the CSV converter to serialize objects into CSV.

Verify the annotation name, package, and registration mechanism against the Spring Cloud Stream version in your project. When upgrading the framework, verify that the converter is still discovered and that selection ordering has not changed unexpectedly.

## 8. Converter Selection and Handling Conflicts

An application may have multiple converters coexisting: JSON, String, byte array, and custom converters. Conflicts can arise if multiple converters claim support for the same MIME type and Java type.

To avoid conflicts:

- Choose a distinct, explicit MIME type for custom formats, such as `text/csv`.
- Restrict `supports(Class<?> clazz)` to the types actually handled by the converter.
- Do not declare a custom converter as supporting `application/json` if you only want to tweak how one DTO is parsed without considering the default JSON converter.
- Verify both inbound and outbound directions; a converter might handle one direction properly but fail on the reverse direction.
- Do not rely on undocumented bean ordering to resolve conflicts.

If you need to customize JSON handling, first consider configuring Jackson, modules, naming strategies, or appropriate serializers/deserializers. Writing a separate JSON converter should only be done when conversion rules genuinely differ from default behavior and are thoroughly tested.

## 9. Distinguishing MessageConverter from Native Encoding/Decoding

Spring Cloud Stream message conversion and binder native serialization are two different processing paths.

With Spring Cloud Stream's message conversion mechanism:

- The function declares a Java type.
- The framework uses content type and `MessageConverter` to convert the payload.
- The binder sends or receives the message representation according to its interface.

With native encoding/decoding, the binder uses the broker's or client's own serializer/deserializer. Properties such as `useNativeEncoding` and `useNativeDecoding` can enable this behavior on binders that support it:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            use-native-encoding: true
        receiveOrder-in-0:
          consumer:
            use-native-decoding: true
```

When using native encoding/decoding, do not assume a custom `MessageConverter` will be invoked along that data path. Configure serializers/deserializers and schema strategies according to the binder. For example, with Kafka, configure Kafka serializers/deserializers and schema registry integration according to the library in use.

Choose one clear conversion mechanism per binding. If both a custom converter and native serialization are configured, verify actual ordering and responsibility to prevent double conversion or unexpectedly bypassing a converter.

## 10. Testing Converters

A converter should be unit-tested independently before testing through a binder. Important cases include:

1. Converting valid CSV into the expected Java object.
2. Converting a Java object into a consistently formatted CSV string.
3. Rejecting payloads with missing fields, extra fields, or wrong data types.
4. Rejecting unsupported payload types.
5. Handling charsets and incorrect content types.
6. Ensuring the converter does not hijack MIME types belonging to other converters.
7. Verifying required content types and headers through an actual binding.

Example unit test for the converter:

```java
class OrderCsvMessageConverterTest {

    private final OrderCsvMessageConverter converter =
        new OrderCsvMessageConverter();

    @Test
    void convertsCsvToOrder() {
        Message<byte[]> message = MessageBuilder
            .withPayload(
                "order-1007,customer-42,125000".getBytes(StandardCharsets.UTF_8)
            )
            .setHeader(MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.parseMimeType("text/csv"))
            .build();

        OrderCreated event =
            (OrderCreated) converter.fromMessage(message, OrderCreated.class);

        assertThat(event.orderId()).isEqualTo("order-1007");
        assertThat(event.customerId()).isEqualTo("customer-42");
        assertThat(event.total()).isEqualByComparingTo("125000");
    }
}
```

This example tests the inbound direction directly. Add tests for the outbound direction and invalid data cases as well. Converter APIs and `MessageHeaders` initialization may vary slightly across Spring Framework versions; keep imports and dependencies aligned with your project version.

After unit tests, you can use the Spring Cloud Stream Test Binder to verify the converter is discovered and applied in bindings. The Test Binder does not prove a real broker preserves headers or runs native serialization as configured. If the application depends on serializers, partition keys, a schema registry, or header mapping in Kafka/RabbitMQ/Pulsar, write integration tests against the corresponding broker.

## 11. Diagnosing Conversion Errors

Some common errors:

| Symptom | Possible cause | How to check |
|---|---|---|
| No suitable converter found | Content type or Java type is not supported by any converter | Check `content-type`, function type, and converter MIME types |
| JSON does not map to DTO | Field names, data types, or constructors are incompatible | Check payload, DTO, and Jackson configuration |
| Custom converter is not invoked | Bean not registered properly or binding uses a different content type | Check `@StreamMessageConverter`, bean definition, and binding config |
| Received payload is still `byte[]` | Function expects raw data or native decoding is enabled | Check function signature and binder configuration |
| Outbound conversion has wrong format | Output binding uses wrong content type or converter does not support payload | Check output content type and `supports()` |
| Conversion succeeds in Test Binder but fails with broker | Differences in native serialization, header mapping, or client serializers | Run integration tests with a real broker |

When handling errors, log the content type, binding name, payload type, and target type. Avoid logging the full payload if data may contain sensitive information. Logs should help identify which converter was selected without leaking business content.

## 12. Checklist Before Deploying a Converter to Production

- Define content type and Java types for both inbound and outbound directions.
- Use default converters if they already meet requirements.
- Scope custom converters strictly to supported MIME types and Java types.
- Register converters via `@StreamMessageConverter` beans compatible with your version.
- Check content types in both binding configuration and message headers.
- Handle malformed payloads with explicit exceptions instead of returning dummy objects.
- Bound data size and validate charset, structure, and values.
- Do not confuse `MessageConverter` with binder native serializers/deserializers.
- Run unit tests, Test Binder tests, and real broker tests covering all behaviors the application relies on.

`MessageConverter` helps Spring Cloud Stream convert data between the broker and function Java types. The framework selects a converter based on content type and data type support; applications only need to register custom converters for specialized formats or conversion rules. When content types, function signatures, converters, and native serialization settings are aligned, data conversion becomes predictable and easier to test.
