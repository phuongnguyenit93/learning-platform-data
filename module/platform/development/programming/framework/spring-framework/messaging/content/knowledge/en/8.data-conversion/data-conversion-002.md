# Distinguishing MessageConverter from ConversionService in Spring

## 1. Two Abstractions Solving Two Different Problems

Spring has multiple data conversion mechanisms. Two abstractions that are easily confused are `MessageConverter` in Spring Messaging and `ConversionService` in Spring Core.

Both can convert a value from one form to another, but their scopes of responsibility differ:

- **MessageConverter** operates at the messaging boundary. It converts an object into a `Message<?>` or extracts the payload from a message and converts it into the Java type requested by the receiver. A message can carry headers such as Content-Type, destination, and correlation ID.
- **ConversionService** converts between Java types. It accepts a source object and a target type, then finds an appropriate converter. It does not create messages, does not manage headers, and does not decide how payloads are represented on the wire.

You can remember it concisely as: **MessageConverter converts across the message boundary; ConversionService converts between Java data types.**

After this lesson, you should be able to:

- Accurately describe the responsibilities and APIs of both abstractions.
- Distinguish payload conversion from object-to-object conversion.
- Choose a converter based on Content-Type, payload, and target type.
- Register converters for ConversionService without confusing them with the MessageConverter list.
- Understand how a MessageConverter can use ConversionService internally.
- Design conversion flows that are easy to test and do not mix serialization with business rules.

## 2. MessageConverter: Conversion at the Messaging Boundary

### 2.1 API Contract

The `org.springframework.messaging.converter.MessageConverter` interface has two core methods:

~~~java
Message<?> toMessage(Object payload, MessageHeaders headers);

<T> T fromMessage(Message<?> message, Class<T> targetClass);
~~~

- `toMessage` creates a message from a payload and headers. The converter may add metadata needed for the message representation.
- `fromMessage` reads the message and converts the payload into the requested target class.
- If the converter does not support the conversion case, it may return `null` to indicate it cannot handle that message.

The key point is that MessageConverter operates on the **entire message context**. Beyond the payload type, the converter can inspect Content-Type to determine how to serialize or deserialize the data.

For example, an application sending a DTO through a broker can serialize the object to JSON, set Content-Type to `application/json`, and send the message. On the receiving side, the converter reads Content-Type and converts the payload into the corresponding DTO.

### 2.2 Common Converters

| Converter | Usage scope |
|---|---|
| `StringMessageConverter` | Converts String text payloads |
| `ByteArrayMessageConverter` | Preserves or creates byte[] payloads |
| `MappingJackson2MessageConverter` | Converts objects and JSON using Jackson in supported versions |
| `MarshallingMessageConverter` | Converts via Spring OXM marshaller/unmarshaller |
| `GenericMessageConverter` | Uses ConversionService to convert payloads between Java types |

Which MIME types a specific converter supports depends on the implementation and configuration. For example, StringMessageConverter defaults to text/plain; ByteArrayMessageConverter fits application/octet-stream. JSON converters handle JSON content according to the mapper configuration and supported MIME types.

Not every MessageConverter serializes every object. Check the payload type, Content-Type, and the list of converters registered on the actual endpoint or template.

### 2.3 Example: Converting a Text Message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class MessageConverterDemo {

    public static void main(String[] args) {
        StringMessageConverter converter = new StringMessageConverter();

        Message<String> incoming = MessageBuilder
                .withPayload("order.created")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN)
                .build();

        String payload = converter.fromMessage(incoming, String.class);

        Message<?> outgoing = converter.toMessage(
                payload,
                incoming.getHeaders());

        System.out.println(payload);
        System.out.println(outgoing.getHeaders()
                .get(MessageHeaders.CONTENT_TYPE));
    }
}
~~~

Output:

~~~text
order.created
text/plain
~~~

The example demonstrates both directions: reading a payload from a message as a String, then creating a new message from the String and headers. The converter operates within the messaging context and preserves appropriate Content-Type information.

## 3. ConversionService: Conversion Between Java Types

### 3.1 API Contract

`org.springframework.core.convert.ConversionService` provides a general API to check and perform object conversions:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

In addition to overloads accepting Class, the API supports `TypeDescriptor` to describe types in greater detail, which is useful for generic types, collections, and property metadata.

ConversionService does not know which channel a message came from, does not read destinations, and does not create headers. It only cares about source type and target type.

Main components:

- **ConversionService:** interface used to check and perform conversions.
- **Converter<S, T>:** simple converter from type S to type T.
- **ConverterFactory<S, R>:** creates converters for a family of target types sharing a common base type.
- **GenericConverter:** supports multiple source/target type pairs and TypeDescriptor.
- **ConfigurableConversionService:** allows registering converters.
- **DefaultConversionService:** built-in implementation with many common converters and support for adding custom converters.

ConversionService is used in many parts of Spring such as binding, configuration, expressions, and in-application data conversion. Its actual scope depends on the bean or instance configured for that component.

### 3.2 Example: Converting String to a Domain Type

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

public class ConversionServiceDemo {

    record OrderId(String value) {
    }

    public static void main(String[] args) {
        DefaultConversionService conversionService =
                new DefaultConversionService();

        conversionService.addConverter(
                String.class,
                OrderId.class,
                OrderId::new);

        boolean supported = conversionService.canConvert(
                String.class,
                OrderId.class);

        OrderId orderId = conversionService.convert(
                "ORD-42",
                OrderId.class);

        System.out.println(supported);
        System.out.println(orderId.value());
    }
}
~~~

Output:

~~~text
true
ORD-42
~~~

Here there is no message, channel, or headers. ConversionService simply converts the string `ORD-42` into an `OrderId` object. This is pure Java type conversion.

### 3.3 Registering a Converter

A custom converter can be declared using the `Converter<S, T>` interface:

~~~java
import org.springframework.core.convert.converter.Converter;

public class StringToOrderIdConverter
        implements Converter<String, OrderId> {

    @Override
    public OrderId convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Order ID is required");
        }

        return new OrderId(source.trim());
    }
}
~~~

Then register the converter with a configurable ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToOrderIdConverter());
~~~

In a Spring application, you can declare and inject a ConversionService suited to the needed scope. Do not create a separate instance inside every method if the application needs to share a single managed set of conversion rules.

## 4. Direct Comparison

| Criterion | MessageConverter | ConversionService |
|---|---|---|
| Package | `org.springframework.messaging.converter` | `org.springframework.core.convert` |
| Input | Payload and/or Message | Java object |
| Output | Message or payload matching target type | Object of target type |
| Headers | Can read or create headers | Does not manage headers |
| Content-Type / MIME | Meaningful in message selection and representation | Not a core concept |
| Serialization | Can serialize/deserialize payloads | Does not define wire formats itself |
| Example | DTO ↔ JSON Message | String → OrderId |
| Context | Messaging, channels, adapters, templates | Binding, type conversion, Spring applications |

Consider the same string `"42"`:

- ConversionService can convert String to Integer if a matching converter is registered.
- MessageConverter can read a payload from a Message with a matching Content-Type and return a String or object depending on the converter's capabilities.
- A JSON MessageConverter can deserialize JSON into a DTO; ConversionService by default is not a JSON parser.

Do not use the two abstractions interchangeably just because both contain the word “converter”.

## 5. How Can They Work Together?

Some MessageConverters use ConversionService to perform the payload conversion step. `GenericMessageConverter` is a clear example: it relies on ConversionService to convert the payload from its current type to the target class.

Combined flow:

~~~text
Message<?> from channel
        |
        v
MessageConverter.fromMessage(...)
        |
        | reads payload + headers
        v
GenericMessageConverter
        |
        v
ConversionService.convert(source, targetType)
        |
        v
Java object of target type
~~~

In this case:

1. MessageConverter receives the message and identifies the payload to convert.
2. GenericMessageConverter invokes ConversionService with the source object and target type.
3. ConversionService locates the matching Converter.
4. The converted object is returned as the result of fromMessage.

This does not mean every MessageConverter uses ConversionService. JSON converters typically rely on an ObjectMapper or dedicated serializer. Text converters have their own charset logic. Each implementation has its own internal mechanism.

### 5.1 Example: GenericMessageConverter Using ConversionService

~~~java
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

public class GenericMessageConversionDemo {

    record OrderId(String value) {
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(String.class, OrderId.class, OrderId::new);

        GenericMessageConverter converter =
                new GenericMessageConverter(service);

        Message<String> message = MessageBuilder
                .withPayload("ORD-99")
                .build();

        OrderId orderId = converter.fromMessage(
                message,
                OrderId.class);

        System.out.println(orderId.value());
    }
}
~~~

Output:

~~~text
ORD-99
~~~

The example shows the two layers collaborating: GenericMessageConverter handles the Message context, while ConversionService performs the conversion from String to OrderId.

## 6. When to Choose Which Abstraction?

### 6.1 Use MessageConverter when

- Reading messages from a channel or adapter into Java payloads.
- Sending objects as messages via templates or adapters.
- Needing to serialize DTOs to JSON, XML, or another representation.
- Needing to consider Content-Type, MIME type, or charset.
- Needing to preserve or set protocol-appropriate metadata.

### 6.2 Use ConversionService when

- Converting Strings to enums, numbers, dates, or domain types.
- Converting property values during binding.
- Converting argument types or data between Java classes.
- Reusing type conversion rules across multiple Spring components.
- Wanting to register Converter, ConverterFactory, or GenericConverter.

### 6.3 When both are needed

An application may need both in the same flow:

1. The adapter receives a JSON message.
2. MessageConverter deserializes JSON into a DTO.
3. The service validates contracts and business rules.
4. ConversionService converts a String field into a specialized domain type if needed.
5. The service executes business logic.
6. MessageConverter serializes the result into an outbound message.

Do not place business logic inside converters. Converters should focus on data representation and conversion. Whether an order ID exists as valid in the system or whether a user has permission to act on the order is the responsibility of validation and business services.

## 7. Configuration in Spring and Spring Boot

### 7.1 Registering ConversionService

In a Spring application, you can declare a ConversionService bean or use an implementation provided by the framework. Actual configuration depends on the consuming component: Spring MVC, data binding, configuration properties, or messaging adapters may each have their own registry and lifecycle.

Example bean declaration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.DefaultConversionService;

@Configuration
public class ConversionConfiguration {

    @Bean
    public DefaultConversionService applicationConversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(
                String.class,
                OrderId.class,
                OrderId::new);

        return service;
    }
}
~~~

The bean above is only used by components that reference that bean or are configured to receive it. Do not assume every converter registry in the application automatically shares the same instance.

### 7.2 Registering MessageConverter

The MessageConverter list is configured per messaging component in use. For example, Spring WebSocket/STOMP has its own mechanism for configuring message converters; other templates or adapters may also accept their own converter lists.

When configuring, determine:

- Which converter supports the flow's payload and MIME type.
- Which converter is tried first if multiple converters are compatible.
- Which ObjectMapper or serializer is used for JSON.
- How Content-Type is produced and propagated across the adapter.
- Whether the converter is configured for inbound, outbound, or both.

Registering a ConversionService does not automatically register a MessageConverter for STOMP, JMS, AMQP, or Kafka. Likewise, adding a MessageConverter to an adapter does not alter the ConversionService used in application binding.

## 8. Error Handling and Checking Conversion Capability

### 8.1 With MessageConverter

If a converter does not support the payload, Content-Type, or target class, the result may be `null`. Depending on the calling component, failing to find a converter can lead to a conversion error or a message processing failure.

Check:

- Is the actual payload of the expected type?
- Is the Content-Type compatible with the converter?
- Does the target class match the message contract?
- Is the converter registered on the right adapter/template?
- Does the serializer handle the current schema/version?

### 8.2 With ConversionService

Use `canConvert` beforehand if the application needs to verify conversion capability:

~~~java
if (!conversionService.canConvert(String.class, OrderId.class)) {
    throw new IllegalStateException("No converter for OrderId");
}
~~~

If no suitable converter exists, `convert` may throw `ConversionFailedException` or an exception in the ConversionException hierarchy. If a converter validates input data and throws an exception, distinguish invalid input errors from missing converter errors.

Do not catch every exception and return null because doing so can hide configuration errors or invalid data.

## 9. Testing the Two Abstractions Separately

### 9.1 Testing ConversionService

Verify source type, target type, converted values, and invalid inputs. For example, an empty String should not become a valid OrderId if the domain forbids it.

### 9.2 Testing MessageConverter

Verify:

- Payload and Content-Type after toMessage.
- Target type after fromMessage.
- Charset with Unicode data.
- Unsupported MIME types.
- Incompatible JSON schemas.
- Whether the converter returns null or throws errors per contract.

### 9.3 Integration Testing

When a MessageConverter uses ConversionService, test both layers:

1. ConversionService has converters for the required source/target types.
2. MessageConverter actually invokes that conversion mechanism during the message flow.
3. The adapter or template has registered the right converter.
4. Headers and Content-Type are preserved or mapped properly.

Unit tests for ConversionService do not prove that a broker adapter has configured MessageConverter. Integration tests against real endpoints verify messaging wiring.

## 10. Common Mistakes

- **Treating MessageConverter and ConversionService as the same thing:** one handles Messages and payloads, the other handles Java type conversion.
- **Assuming ConversionService parses JSON automatically:** a dedicated JSON serializer/deserializer is needed.
- **Thinking MessageConverter only converts Java objects:** it also deals with headers, Content-Type, and the message envelope.
- **Registering ConversionService while forgetting MessageConverter:** the adapter may still not know how to serialize payloads.
- **Registering MessageConverter on the wrong adapter:** each endpoint or template may maintain its own converter registry.
- **Ignoring Content-Type:** the converter is not selected or decodes the wrong format.
- **Putting business rules into converters:** makes data conversion depend on domain state and harder to reuse.
- **Failing to check for null or exceptions:** conversion failures are hidden and hard to trace.
- **Assuming one ConversionService bean is used everywhere automatically:** individual framework components may use separate registries.
- **Not testing converter ordering:** a general converter may claim data before a specialized converter runs.

## 11. Selection Checklist

Before implementing conversion, answer:

- Is the input a Message or a plain Java object?
- Is reading or creating headers and Content-Type required?
- Is serializing/deserializing JSON, XML, or binary required?
- Is only source-type-to-target-type conversion needed, or is handling the message envelope required?
- Has the converter been registered on the right adapter/template?
- Does ConversionService support the source/target types?
- If multiple converters match, is the selection order clear?
- How are malformed data, MIME mismatches, and unsupported target types handled?
- Are there separate tests for each abstraction and integration tests for the combined flow?

When the two responsibilities are separated cleanly, MessageConverter handles how data crosses the messaging boundary, while ConversionService provides conversion rules between Java types. Both abstractions can collaborate within the same flow while maintaining clear scopes, making the system easier to extend, test, and maintain.