# Generic Target Types, Method Metadata, and Conversion Hints

## 1. The Problem: Knowing What the Payload Is and What Type the Consumer Needs

In Spring Messaging, `Message<T>` indicates the expected payload type on the Java code side. However, when a message passes through a converter or transport, the data may currently be a `String`, `byte[]`, or another representation. The converter must know the target Java type to convert the payload into an object the handler can use.

For simple types like `Order`, the `Class<Order>` parameter is usually sufficient. For generic types such as `List<Order>`, `Map<String, List<Order>>`, or `Envelope<Payment>`, `Class<?>` only holds the raw type at runtime. `List.class` does not carry the information that its element type is `Order`; due to type erasure, a converter cannot infer generic arguments from `List.class` alone.

Spring provides tools to preserve target type information:

- `MethodParameter`: describes a method parameter, including generic type and annotations.
- `ResolvableType`: represents a type that can carry generic arguments and supports type variable resolution.
- `SmartMessageConverter`: extends `MessageConverter` with a `conversionHint` parameter so callers can pass additional metadata into the conversion process.

These three components solve three separate parts: method metadata states what the handler declares it receives; `ResolvableType` represents that type; the conversion hint delivers the necessary information to the converter.

## 2. Why Is Class<?> Not Enough for Generic Types?

Example:

~~~java
void handleOrders(List<Order> orders) {
    // process list of Orders
}
~~~

When reflecting on the method, `List.class` is only the raw class. Both `List<Order>` and `List<Customer>` have the raw class `List.class`. If a converter only receives `targetClass=List.class`, it cannot tell whether to instantiate `Order` or `Customer` elements.

The same problem occurs with nested types:

~~~java
Map<String, List<Order>> ordersByRegion;
Envelope<Payment> paymentEvent;
~~~

Accurate conversion requires preserving the entire generic type tree, not just the outermost class name. Without generic metadata, a JSON converter may produce a `List` containing `LinkedHashMap` instances instead of `List<Order>`. The error might only surface later when code casts an element.

Do not solve this by guessing types from field names or JSON data. The target type must come from the consumer contract, endpoint configuration, or controlled metadata.

## 3. MethodParameter: Extracting Types from Method Signatures

`org.springframework.core.MethodParameter` describes a specific parameter of a method or constructor. It retains reflection information such as:

- The containing `Method`/constructor and the parameter index.
- The declared parameter type, including its generic signature.
- Annotations placed on the parameter.
- Parameter name information if compilation metadata allows retrieval.

For example, given the method:

~~~java
void handleOrders(List<Order> orders) {
}
~~~

you can create metadata for the first parameter:

~~~java
Method method = Handler.class.getDeclaredMethod("handleOrders", List.class);
MethodParameter parameter = new MethodParameter(method, 0);
~~~

Index `0` is the first parameter. `MethodParameter` does not convert payloads itself; it supplies information so an argument resolver or converter knows the type the handler requires.

Method metadata can also carry annotations used for conversion rules. For example, a custom annotation can specify a date format or deserialization rule. Converters should only honor annotations with explicit contracts; avoid using reflection to infer business logic.

## 4. ResolvableType: Preserving Generic Arguments

`org.springframework.core.ResolvableType` represents a Java type along with resolvable generic information. It can be created from a `MethodParameter`:

~~~java
ResolvableType targetType = ResolvableType.forMethodParameter(parameter);
Class<?> rawType = targetType.resolve();
Class<?> elementType = targetType.getGeneric(0).resolve();
~~~

For a `List<Order>` parameter, `rawType` is `List.class`, and the first generic resolves to `Order.class`.

For nested types, you can navigate deeper across each generic argument:

~~~java
ResolvableType type = ResolvableType.forMethodParameter(parameter);
ResolvableType valueType = type.getGeneric(1);
ResolvableType elementType = valueType.getGeneric(0);
~~~

If the declared type is `Map<String, List<Order>>`, the first generic is `String`, the second generic is `List<Order>`, and the first generic of that value type is `Order`.

`ResolvableType` can also be created from a class, field, method return type, or type reference. When a type variable is not yet bound by a concrete class/type, `resolve()` may return `null` or an overly general type. In that case, pass an explicit context type or declare a concrete contract.

## 5. MessageConverter and SmartMessageConverter

`MessageConverter` converts between Java payloads and `Message<?>`. The two basic operations are:

- `toMessage(payload, headers)`: creates a message from an object and metadata.
- `fromMessage(message, targetClass)`: converts a message's payload into the target Java type.

`SmartMessageConverter` extends these two operations with overloads taking an extra `conversionHint`:

~~~java
Message<?> toMessage(Object payload, MessageHeaders headers, Object conversionHint);
Object fromMessage(Message<?> message, Class<?> targetClass, Object conversionHint);
~~~

`conversionHint` is additional metadata passed by the caller. It can be a `MethodParameter`, `ResolvableType`, or an application-defined hint object. A converter must check the hint type before using it and have a clear fallback if the hint is unsupported.

Not every converter uses hints. If you use a `MessageConverter` that only supports `Class<?>`, generic information can be lost. When generic target types are needed, choose or implement `SmartMessageConverter` and ensure the call path actually forwards the hint to the converter.

### 5.1. A hint is not a header

`conversionHint` is an argument in a Java call to the converter. It does not appear in `MessageHeaders`, is not serialized with the payload, and does not travel across a broker.

This matters for inter-process messaging: a `MethodParameter` holding a receiving application's reflection object cannot be sent from producer to broker as part of a contract. The consumer must determine the target type from its own method/endpoint, schema configuration, or a controlled registry.

Do not put `MethodParameter` or `ResolvableType` objects into headers expecting the broker to transmit that Java metadata intact.

## 6. Content Type, Target Type, and Conversion Hint Are Three Different Things

| Information | Question answered | Examples |
| --- | --- | --- |
| Content type | What format represents the payload? | `application/json`, `text/plain`, `application/octet-stream` |
| Target type | What Java object type does the consumer want? | `Order.class`, `List.class`, `Map.class` |
| Generic type metadata | What are the generic arguments of the target type? | `List<Order>`, `Map<String, List<Order>>` |
| Conversion hint | Is there metadata helping the converter choose how to interpret it? | `MethodParameter`, `ResolvableType`, annotations, or custom hints |

For example, `contentType=application/json` only says the payload is JSON. It does not say whether that JSON should become `List<Order>` or `List<Customer>`. The raw target class `List.class` also does not retain the generic element type. The converter needs an additional hint or a known target schema/type.

In Spring Messaging, `MessageHeaders.CONTENT_TYPE` is the standard header for describing content type. Use values matching the actual representation. Attaching `application/json` does not automatically serialize a Java object to JSON; the serializer/converter must perform that work.

## 7. Conversion Flow in a Method-Based Endpoint

A typical processing path can be visualized as follows:

~~~text
Transport / MessageChannel
        |
        v
Message<?> (payload + headers)
        |
        v
Endpoint / argument resolver
        |  reads handler signature
        |  creates MethodParameter
        |  creates ResolvableType
        v
SmartMessageConverter.fromMessage(
    message, rawTargetClass, conversionHint)
        |
        v
Java object of exact target type
        |
        v
Handler method
~~~

This is a conceptual model. Exactly which adapter/endpoint constructs `MethodParameter`, passes what hint, and selects which converter depends on the Spring module in use. Do not assume every `MessageChannel` or every handler automatically uses the same conversion pipeline.

## 8. How Does ConversionService Differ from MessageConverter?

Spring Core's `ConversionService` focuses on converting a Java value from a source type to a target type, such as `String` to `Integer` or an enum to a string. It can be used inside argument resolution or converters.

`MessageConverter` operates at the message boundary: it receives the full `Message<?>`, can inspect headers/content type, and converts the payload to the target type or builds a message from a payload.

`SmartMessageConverter` adds conversion hints so converters can leverage generic types, method metadata, or extra conversion information.

Do not equate these three abstractions. `ConversionService` does not replace JSON deserialization; `MessageConverter` does not decide channels/handlers; `SmartMessageConverter` does not provide persistence or delivery guarantees.

## 9. Building a Converter Supporting Generic Types

A converter supporting generic targets should:

1. Identify the payload representations it supports, such as JSON as `String` or `byte[]`.
2. Inspect content type when present and reject unsupported formats.
3. Determine the target type from the conversion hint first; if no hint is present, fall back to `targetClass`.
4. Translate the full generic type into a type understood by the serializer library.
5. Check results and report conversion errors clearly when JSON is malformed or the target type mismatches.
6. Never infer target types from untrusted data or arbitrary class names sent by a producer.

With Jackson, `JavaType` represents the target type used by `ObjectMapper` during deserialization. You can construct a `JavaType` from `ResolvableType.getType()` via `TypeFactory.constructType(...)`. This preserves generic signatures like `List<Order>` instead of using `List.class` alone.

### 9.1. Fallback when no hint is provided

If a converter receives neither `MethodParameter` nor `ResolvableType`, it can use `ResolvableType.forClass(targetClass)`. This fallback suffices for non-generic targets like `Order.class`.

For raw `List.class`, the fallback cannot know the element type. It can return a collection of maps/objects per serializer behavior, or decline conversion if the contract requires strongly typed elements. Do not silently pretend generic type information was preserved.

## 10. Complete Example: Converting JSON to List<Order> Using MethodParameter

This example uses Java 17, Spring Messaging 6.2.8, and Jackson 2.18.3. The converter only demonstrates the inbound direction from JSON `String` to Java object; the `toMessage` direction returns `null` to show that the demo converter does not support outbound serialization.

Create the Maven project:

~~~text
generic-message-conversion/
  pom.xml
  src/main/java/com/example/messaging/GenericMessageConversionDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>generic-message-conversion</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
        <jackson.version>2.18.3</jackson.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>${jackson.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

`src/main/java/com/example/messaging/GenericMessageConversionDemo.java`:

~~~java
package com.example.messaging;

import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.util.List;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.MethodParameter;
import org.springframework.core.ResolvableType;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.converter.SmartMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public final class GenericMessageConversionDemo {
    private GenericMessageConversionDemo() {
    }

    public record Order(String id, BigDecimal amount) {
    }

    private static void handleOrders(List<Order> orders) {
        // Method signature is used as target-type metadata in this example.
    }

    private static final class JsonHintMessageConverter implements SmartMessageConverter {
        private final ObjectMapper objectMapper = new ObjectMapper();

        @Override
        public Message<?> toMessage(Object payload, MessageHeaders headers) {
            return null;
        }

        @Override
        public Message<?> toMessage(Object payload, MessageHeaders headers, Object conversionHint) {
            return null;
        }

        @Override
        public Object fromMessage(Message<?> message, Class<?> targetClass) {
            return fromMessage(message, targetClass, null);
        }

        @Override
        public Object fromMessage(Message<?> message, Class<?> targetClass, Object conversionHint) {
            if (!(message.getPayload() instanceof String json)) {
                return null;
            }

            ResolvableType targetType;
            if (conversionHint instanceof MethodParameter methodParameter) {
                targetType = ResolvableType.forMethodParameter(methodParameter);
            } else if (conversionHint instanceof ResolvableType resolvableType) {
                targetType = resolvableType;
            } else {
                targetType = ResolvableType.forClass(targetClass);
            }

            JavaType javaType = objectMapper.getTypeFactory().constructType(targetType.getType());
            try {
                return objectMapper.readValue(json, javaType);
            } catch (JsonProcessingException ex) {
                throw new MessageConversionException("Invalid JSON message payload", ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String json = "[{\"id\":\"O-1\",\"amount\":19.95},"
                + "{\"id\":\"O-2\",\"amount\":42.50}]";

        Message<String> message = MessageBuilder
                .withPayload(json)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build();

        Method method = GenericMessageConversionDemo.class
                .getDeclaredMethod("handleOrders", List.class);
        MethodParameter hint = new MethodParameter(method, 0);

        JsonHintMessageConverter converter = new JsonHintMessageConverter();
        Object converted = converter.fromMessage(message, List.class, hint);
        List<?> orders = (List<?>) converted;
        Order first = (Order) orders.get(0);

        ResolvableType targetType = ResolvableType.forMethodParameter(hint);
        System.out.println("targetRawType=" + targetType.resolve().getSimpleName());
        System.out.println("targetElementType=" + targetType.getGeneric(0).resolve().getSimpleName());
        System.out.println("orderCount=" + orders.size());
        System.out.println("firstOrderId=" + first.id());
        System.out.println("firstAmount=" + first.amount().toPlainString());
    }
}
~~~

Compile and run from the directory containing `pom.xml` using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.GenericMessageConversionDemo
~~~

Stdout:

~~~text
targetRawType=List
targetElementType=Order
orderCount=2
firstOrderId=O-1
firstAmount=19.95
~~~

Key points to observe:

- `MessageHeaders.CONTENT_TYPE` describes that the payload is JSON.
- `List.class` provides only the raw target class.
- `MethodParameter` captures the `handleOrders(List<Order>)` signature from reflection.
- `ResolvableType.forMethodParameter(...)` preserves the generic argument `Order`.
- `SmartMessageConverter` receives `MethodParameter` via `conversionHint` and builds the full Jackson `JavaType`.
- The result is a list with `Order` elements, not a list of untyped maps.

The demo converter intentionally omits outbound serialization and returns `null` for `toMessage`. In real applications, implement that direction or use another appropriate converter; do not treat this snippet as a complete bidirectional JSON converter.

## 11. Error Handling and Unresolvable Target Types

Conversion can fail at multiple layers:

| Situation | Cause | How to handle |
| --- | --- | --- |
| Payload in wrong representation | Converter expects JSON `String` but receives `byte[]` or another object | Add support for that representation or decline clearly as unsupported |
| Malformed JSON | Corrupted payload or producer violated the contract | Report conversion error, isolate/DLQ per message policy |
| Missing generic hint | Only `List.class` is available without element type | Provide `MethodParameter`, `ResolvableType`, or an explicit schema target |
| Unbound type variable | Generic method/class lacks concrete context | Resolve using containing type or require an explicit target type |
| Unsupported content type | Header declares XML/binary while converter only reads JSON | Choose the right converter or reject the message |
| Incompatible field types | JSON contains values with wrong types/formats | Check schema, converter config, and producer data |
| Unrecognized hint | Caller passes an unexpected hint object type | Ignore using defined fallback or report a clear configuration error |

Do not return `null` for every error. In the converter contract, `null` normally means the converter does not support converting that message/target; data errors or malformed JSON should be reported with an appropriate exception so the endpoint can apply error handling.

## 12. Generic Type Metadata and Transport Boundaries

`MethodParameter` and `ResolvableType` are typically consumer-side metadata. When a message crosses a broker, the producer cannot assume the consumer shares the same classpath or method signatures.

For inter-service integration:

- Define schemas/wire formats independently of internal Java classes.
- Consumers select target types based on endpoints or a controlled registry.
- Use content type to describe format and schema version to describe contract version.
- If type headers used by framework/broker adapters exist, restrict allowed packages/types for deserialization; do not let untrusted payloads choose arbitrary classes.
- Never serialize `Method`, `MethodParameter`, `ResolvableType`, or Java `Class` objects as part of the message contract.

Generic type hints help a converter inside one process preserve the right target type; they do not replace schema registries, versioning, or validation at service boundaries.

## 13. Common Mistakes

- **Passing only `List.class`:** generic element types are lost and elements may become maps.
- **Confusing content type with target type:** `application/json` does not state whether JSON must become `List<Order>`.
- **Assuming `Message<T>` preserves generics across a broker:** Java generics do not automatically exist in the wire format.
- **Failing to pass conversion hints:** the converter sees only the raw class and cannot build the proper generic type.
- **Assuming every MessageConverter uses hints:** only `SmartMessageConverter` provides hint overloads; callers must also invoke the right overload.
- **Putting MethodParameter into headers:** reflection metadata is internal consumer info, not a transport contract.
- **Guessing target types from class names sent by producers:** can introduce deserialization vulnerabilities and classpath coupling.
- **Not handling unresolved type variables:** converters may silently fall back to `Object` or an overly broad type.
- **Returning null for malformed payloads:** causes data errors to be mistaken for unsupported converters.
- **Not validating objects after conversion:** a valid Java type does not guarantee data satisfies business invariants.

## 14. Design and Review Checklist

1. Does the consumer need a simple type or a nested generic type?
2. Is `targetClass` sufficient to express the target type?
3. If the target is generic, does metadata come from `MethodParameter`, `ResolvableType`, or which schema/configuration?
4. Does the caller pass the hint to the `SmartMessageConverter` overload?
5. Does the converter inspect the hint type and fall back cleanly?
6. Does `ResolvableType` resolve generic arguments, or are unbound type variables remaining?
7. Does content type match the actual representation?
8. Does the serializer translate the target type into a complete `JavaType`/type token?
9. Are JSON, field type, format, and schema errors categorized accurately?
10. Are hints ever confused with headers or transport metadata?
11. Are allowed types restricted when deserializing external messages?
12. Does the consumer validate business invariants after conversion?

## 15. Key Takeaways

`Class<?>` describes a raw target type and does not retain generic arguments like `List<Order>`. `MethodParameter` extracts parameter details from method signatures, while `ResolvableType` represents and resolves generic types. `SmartMessageConverter` adds `conversionHint` so callers can pass `MethodParameter`, `ResolvableType`, or other conversion metadata to converters. Content type describes the payload format; target type describes the Java object the consumer needs; conversion hints supply extra info for accurate conversion. Hints are internal call metadata and do not automatically traverse brokers. For inter-service messaging, use schema/versioning and consumer-controlled target types; do not rely on reflection objects or arbitrary class names from producers.