# GenericMessageConverter and Type Conversion via ConversionService

In Spring Messaging, a message has a payload and headers. Payloads can come from many sources with different data types: String, numbers, byte arrays, or a Java object. When a consumer needs a specific Java type, Spring can convert the payload from the source type to the target type before passing it to business logic.

GenericMessageConverter is a MessageConverter that uses ConversionService to perform payload type conversion. It is suitable for conversions between Java types supported by ConversionService, such as String to Integer or String to an application-defined domain type.

Distinguish Java type conversion from decoding a data format like JSON. GenericMessageConverter is not a JSON serializer/deserializer. It does not automatically parse a JSON string into an object merely because a message has contentType header `application/json`.

## 1. Three Components to Understand

### 1.1. MessageConverter

org.springframework.messaging.converter.MessageConverter is the payload conversion contract for Spring Messages.

The contract has two primary operations:

- fromMessage(message, targetClass): extracts the payload from the message and converts it to type targetClass.
- toMessage(payload, headers): creates a Message from a payload and optional headers.

The result of fromMessage is a converted object, not a new Message. If the converter does not support the requested type or format, the contract allows returning null to indicate the converter cannot handle that message.

The contentType header can describe the content's MIME type, such as text/plain or application/json. A converter can use this header to choose how to interpret the payload. However, having a contentType does not perform conversion by itself; the invoked converter must actually support the corresponding MIME type and format.

### 1.2. ConversionService

org.springframework.core.convert.ConversionService is the API for converting between Java types. It answers two questions:

- canConvert(sourceType, targetType): is there a suitable converter for this pair of types?
- convert(source, targetType): performs the conversion and returns an object of the target type.

ConversionService is a facade over a set of registered converters. It decouples conversion logic from calling code, allowing multiple components to share a single set of type conversion rules.

For example, a ConversionService may know how to convert:

- String to Integer or Long.
- String to Boolean, UUID, or enum.
- A domain type to String.
- An application-defined source type to another target type.
- Collections or arrays to another collection/array type when a matching element converter exists.

ConversionService does not understand arbitrary serialization formats on its own. It operates on Java objects already in memory.

### 1.3. GenericMessageConverter

org.springframework.messaging.converter.GenericMessageConverter extends SimpleMessageConverter and uses ConversionService to convert payloads to the requested target type.

It has two constructors:

~~~java
new GenericMessageConverter()
~~~

Creates a converter with the default ConversionService.

~~~java
new GenericMessageConverter(conversionService)
~~~

Creates a converter with an application-provided ConversionService. The second form fits when the application has custom converters or needs consistent conversion rules across multiple components.

GenericMessageConverter primarily adds conversion to the fromMessage operation. The toMessage method is inherited from SimpleMessageConverter and merely wraps the payload inside a Message; it does not serialize objects into JSON or byte arrays.

## 2. Payload Conversion Flow

When a consumer requests a Java type different from the current payload type, the general processing flow is as follows:

~~~text
Message<?>
    |
    | extract payload
    v
Source object
    |
    | GenericMessageConverter.fromMessage(...)
    v
ConversionService
    |
    | find converter for source type -> target type
    v
Converted object
    |
    v
Consumer business processing
~~~

For example, a message has a payload string `"42"`. The consumer needs an Integer. GenericMessageConverter extracts the String from the payload, then delegates to ConversionService to convert the String into an Integer.

If the payload is already compatible with targetClass, the converter can return the payload without conversion. If ConversionService finds no matching converter, GenericMessageConverter returns null. If a converter exists but the input data is invalid, the convert operation may throw ConversionException; the application must handle this error according to the message flow's policy.

GenericMessageConverter only converts the payload. It does not rename headers, modify MessageHeaders, or confirm that a message was delivered by a broker.

## 3. How Do SimpleMessageConverter and GenericMessageConverter Differ?

SimpleMessageConverter only unwraps the payload if the payload already belongs to the desired target type; in the reverse direction, it wraps the payload into a Message. It does not perform real type conversion and ignores content type information in headers.

GenericMessageConverter inherits that basic behavior while also using ConversionService to convert the payload to targetClass when needed.

| Criterion | SimpleMessageConverter | GenericMessageConverter |
|---|---|---|
| Payload already matches target type | Returns payload | Returns payload |
| String to Integer | Does not convert automatically | Yes if ConversionService supports it |
| Domain type with custom Converter | Not handled automatically | Yes if converter is registered |
| toMessage | Wraps payload into Message | Inherits payload wrapping behavior |
| JSON text to POJO | No | Not automatically |
| Relies on ConversionService | No | Yes for payload conversion in fromMessage |

Choose SimpleMessageConverter when producer and consumer already agree on payload types. Choose GenericMessageConverter when coercion or Java type conversion via ConversionService is needed. For JSON, XML, Protobuf, or a specific serialized format, use a converter specialized for that format.

## 4. Using Built-in Conversions

DefaultConversionService is an implementation containing commonly used default converters. GenericMessageConverter can accept a DefaultConversionService to convert basic types.

Example converting String to Integer:

~~~java
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

public class BasicConversionDemo {

    public static void main(String[] args) {
        GenericMessageConverter converter =
                new GenericMessageConverter(new DefaultConversionService());

        Message<String> message = MessageBuilder
                .withPayload("42")
                .build();

        Integer quantity = (Integer) converter.fromMessage(
                message,
                Integer.class
        );

        System.out.println(quantity);
    }
}
~~~

Output:

~~~text
42
~~~

This is an example of in-memory payload conversion. The message has a String payload; the consumer requests Integer; GenericMessageConverter uses ConversionService to return an Integer.

If the payload is already an Integer, the converter does not need to parse it again. If the payload is a string that does not represent a valid integer, the default converter may throw a conversion error. Never assume every input is valid simply because canConvert returns true.

## 5. Registering a Custom Converter

When the source or target type belongs to the application domain, you can register a Converter<S, T> with ConversionService.

Converter<S, T> describes a source-type and target-type pair. For example, an application has an OrderCode type represented externally by strings like ORD-42.

~~~java
public record OrderCode(String value) {
    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{1,10}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
~~~

Register the converter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        OrderCode.class,
        OrderCode::new
);
~~~

Create GenericMessageConverter with the configured ConversionService:

~~~java
GenericMessageConverter converter =
        new GenericMessageConverter(conversionService);
~~~

Now a String payload can be converted to OrderCode:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-42")
        .build();

OrderCode orderCode = (OrderCode) converter.fromMessage(
        message,
        OrderCode.class
);

System.out.println(orderCode.value());
~~~

Output:

~~~text
ORD-42
~~~

A custom converter is also a suitable place to check formatting, normalize data, or reject invalid values. Do not place complex business logic or database access inside a simple Converter; conversion should focus on representing data between two types.

## 6. Complete Java 17+ Example

The example below combines the built-in String → Integer conversion and custom String → OrderCode conversion in a single program.

~~~java
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

public class GenericMessageConverterDemo {

    public record OrderCode(String value) {
        public OrderCode {
            if (value == null || !value.matches("ORD-[0-9]{1,10}")) {
                throw new IllegalArgumentException("Invalid order code");
            }
        }
    }

    public static void main(String[] args) {
        DefaultConversionService conversionService =
                new DefaultConversionService();

        conversionService.addConverter(
                String.class,
                OrderCode.class,
                OrderCode::new
        );

        GenericMessageConverter converter =
                new GenericMessageConverter(conversionService);

        Message<String> quantityMessage = MessageBuilder
                .withPayload("42")
                .build();

        Integer quantity = (Integer) converter.fromMessage(
                quantityMessage,
                Integer.class
        );

        Message<String> orderMessage = MessageBuilder
                .withPayload("ORD-42")
                .build();

        OrderCode orderCode = (OrderCode) converter.fromMessage(
                orderMessage,
                OrderCode.class
        );

        System.out.println(quantity);
        System.out.println(orderCode.value());
    }
}
~~~

Can be compiled and run when spring-messaging and spring-core dependencies are on the classpath:

~~~bash
javac -cp "spring-messaging.jar;spring-core.jar;spring-jcl.jar" GenericMessageConverterDemo.java
java -cp ".;spring-messaging.jar;spring-core.jar;spring-jcl.jar" GenericMessageConverterDemo
~~~

On Linux/macOS, the classpath separator is a colon instead of a semicolon. In Gradle or Maven projects, let the build tool manage transitive dependencies instead of assembling JARs manually.

Stdout:

~~~text
42
ORD-42
~~~

The example illustrates configuring a ConversionService and reusing it across multiple messages. Converters are registered once at startup and can be shared across message-processing components.

## 7. Checking Conversion Capability Yourself

You can use ConversionService directly to check a pair of types before converting:

~~~java
boolean supported = conversionService.canConvert(
        String.class,
        Integer.class
);

Integer value = conversionService.convert("42", Integer.class);
~~~

canConvert only indicates whether a conversion path is registered for the type pair. It does not confirm that specific content is definitely valid. For instance, String can convert to Integer, yet the string `"forty-two"` will still fail during convert.

For collections, arrays, and maps, canConvert may return true based on container types even if an inner element cannot be converted. At runtime, convert may still throw ConversionException. Validate data and handle exceptions at the message-receiving boundary.

GenericMessageConverter returns null when ConversionService cannot convert the payload to targetClass. The application should clearly distinguish three cases:

1. **Conversion succeeded:** an object of the target type is returned.
2. **No matching converter:** the result is null; the converter declined to handle that message.
3. **Converter exists but data is invalid:** conversion throws an exception; input error handling is required.

Do not coerce null into an object or silently drop the message. If the message strictly requires the target type, turn the unsupported case into a meaningful error for logging, retry, or routing to an appropriate error-handling workflow.

## 8. Registering Converter, ConverterFactory, and GenericConverter

Spring offers several abstractions to extend ConversionService.

### 8.1. Converter<S, T>

Use when only a single source-to-target type pair is needed:

~~~java
Converter<String, OrderCode>
~~~

This is the simplest option for conversions such as String to OrderCode or Integer to another domain type.

### 8.2. ConverterFactory<S, R>

Use when one source type can convert to multiple target types in the same family. For example, a factory can take a String and convert it into various enum types. ConverterFactory returns a concrete converter for the requested target type.

### 8.3. GenericConverter

Use when a converter needs to support multiple type pairs or read type metadata via TypeDescriptor. GenericConverter provides a set of ConvertiblePair entries and a convert method accepting sourceType and targetType.

TypeDescriptor can carry generic type information for collections, arrays, maps, or annotations on fields/methods. This is useful when conversion depends on element types or target-site metadata.

Register these converter types via ConverterRegistry or an implementation like DefaultConversionService. Finish configuring the registry before exposing ConversionService for shared use.

## 9. ConversionService and Generic Types

GenericMessageConverter.fromMessage accepts targetClass of type Class<?>. Consequently, this method expresses the target type at the class level, but cannot pass full generic parameters like List<OrderCode> through a plain Class due to Java type erasure.

If you need to convert collections with specific element types, use ConversionService's TypeDescriptor directly or build a dedicated converter that retains full type information.

Example declaring TypeDescriptor for a list of Integers:

~~~java
TypeDescriptor sourceType = TypeDescriptor.forObject(
        List.of("10", "20")
);

TypeDescriptor targetType = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Integer.class)
);

Object converted = conversionService.convert(
        List.of("10", "20"),
        sourceType,
        targetType
);
~~~

When using TypeDescriptor, ConversionService can apply conversion to each element of the collection if the necessary converters are registered. This is the direct Java type conversion API; GenericMessageConverter does not automatically infer every generic type of a method parameter from targetClass.

## 10. Distinguishing Type Conversion from JSON Decoding

This is the easiest point of confusion when using GenericMessageConverter.

Suppose a message has the string payload:

~~~json
{"orderId":"ORD-42","quantity":2}
~~~

The consumer requests OrderEvent.class. GenericMessageConverter does not automatically parse the JSON string into OrderEvent. Default ConversionService is not a JSON parser.

Cases to distinguish:

| Input payload | Target type | Appropriate tool |
|---|---|---|
| String `"42"` | Integer | GenericMessageConverter + ConversionService |
| String `"true"` | Boolean | GenericMessageConverter + ConversionService |
| String `"ORD-42"` | OrderCode | GenericMessageConverter + custom Converter |
| JSON text | OrderEvent | JSON converter, e.g. MappingJackson2MessageConverter with Jackson configured appropriately |
| byte[] containing JSON | OrderEvent | JSON converter supporting bytes/strings and matching content type |
| XML | Domain object | Appropriate XML/marshalling converter |

MessageHeaders.CONTENT_TYPE can help specialized converters determine the MIME type. However, GenericMessageConverter only performs type conversion via ConversionService; it does not turn JSON text into an object merely because of an `application/json` header.

If you need to serialize an object into JSON when sending a message, choose a converter capable of JSON serialization. If you need to deserialize JSON when receiving, choose a converter supporting JSON and the target type. Do not use GenericMessageConverter as a substitute for Jackson, JAXB, or a dedicated serializer.

## 11. Distinguishing Spring Messaging and JMS MessageConverters

There are two interfaces named MessageConverter in different packages:

- org.springframework.messaging.converter.MessageConverter: converts payloads between Spring Messages and Java objects.
- org.springframework.jms.support.converter.MessageConverter: converts between Java objects and jakarta.jms.Message.

They are not the same interface and cannot be swapped directly for each other.

GenericMessageConverter belongs to Spring Messaging. It uses org.springframework.core.convert.ConversionService to convert payloads inside Spring Messages.

JMS converters operate on JMS message types such as TextMessage, BytesMessage, or MapMessage. JmsTemplate uses converters from spring-jms; an application can configure an appropriate JMS converter for payloads sent/received through the broker.

JmsMessagingTemplate bridges Spring Messaging abstractions and JMS. Its existence does not mean GenericMessageConverter automatically becomes a JMS MessageConverter. When a flow traverses JMS, identify the converter at each layer and test the actual mapping.

## 12. Registering and Managing ConversionService in a Spring Application

In a Spring application, ConversionService is typically created at startup, configured with required converters, and then shared across beans. Standard implementations such as DefaultConversionService are designed to be shared once configured.

Bean declaration example:

~~~java
@Configuration
public class ConversionConfiguration {

    @Bean
    public DefaultConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(
                String.class,
                OrderCode.class,
                OrderCode::new
        );

        return service;
    }

    @Bean
    public GenericMessageConverter genericMessageConverter(
            ConversionService conversionService) {

        return new GenericMessageConverter(conversionService);
    }
}
~~~

In real configurations, avoid registering multiple beans named conversionService or creating multiple converter sets with conflicting rules. Clearly identify which ConversionService is used by messaging converters and other framework components.

Custom Converters should be stateless and thread-safe. Do not store request state, principals, or mutable message data inside a shared converter. If per-request information is needed, pass it through processing services or an appropriate context rather than embedding it in a singleton converter.

## 13. Common Errors and How to Handle Them

### 13.1. fromMessage returns null

The usual cause is that ConversionService has no converter for the source type and targetClass. Check the type pair with canConvert and register an appropriate converter if it is a custom domain type.

### 13.2. ConversionException or ConversionFailedException

A converter was found, but the data is invalid—for example, a non-integer string or a malformed order code. Validate input, include clear error messages, and decide whether the message should be retried or routed to an error flow.

### 13.3. Expecting JSON to convert to an object automatically

GenericMessageConverter is not a JSON mapper. Use a specialized converter and verify content type, Jackson dependencies, and converter configuration.

### 13.4. Conversion succeeds in unit tests but fails in integration environments

The ConversionService used in the test may differ from the bean actually injected by the application. Inspect GenericMessageConverter's constructor and the ConversionService bean configured in the ApplicationContext.

### 13.5. Custom converter is not used

Verify the converter was registered before conversion, that source/target types match expectations, and whether a different ConversionService was injected into GenericMessageConverter.

### 13.6. Confusing JMS converters with Spring Messaging converters

Check package imports and where the converter is configured. JmsTemplate accepts converters from spring-jms; GenericMessageConverter belongs to spring-messaging.

### 13.7. Collection contains an element of the wrong type

canConvert at the collection level may return true while convert still fails on an element. Use TypeDescriptor when generic type info is required and validate actual data.

## 14. Checklist for Implementing GenericMessageConverter

1. Identify the actual payload type of the message.
2. Identify the targetClass needed by the consumer.
3. Check the type pair using ConversionService.canConvert.
4. Use built-in converters if the conversion is already supported.
5. Register a custom Converter if the domain type lacks a conversion rule.
6. Use TypeDescriptor when handling collections/maps with generic element types.
7. Handle null returns and exceptions properly.
8. Use separate JSON/XML converters for serialized formats.
9. Verify the right ConversionService is injected into GenericMessageConverter.
10. Distinguish Spring Messaging's MessageConverter interface from spring-jms's.
11. Configure converters before sharing ConversionService across multiple threads.
12. Write tests for valid data, invalid data, and unsupported types.

## 15. References

- [GenericMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html)
- [SimpleMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/SimpleMessageConverter.html)
- [MessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [ConversionService — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [DefaultConversionService — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring JMS — Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms.html)

GenericMessageConverter handles payload conversion between Java types via ConversionService. When processing JSON, XML, or a specific serialization protocol, choose the converter matching that format and maintain clear boundaries between type conversion, serialization, and transport.