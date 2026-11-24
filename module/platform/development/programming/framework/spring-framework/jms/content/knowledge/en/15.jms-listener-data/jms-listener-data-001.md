# Payload Parameters and @Payload in @JmsListener

**Topic:** Spring Framework - jms → Listener Data

## 1. What Is a Payload and Why Does a Listener Need a Payload Parameter?

In a JMS (Jakarta Messaging) system, each message typically has three parts:

- **Standard JMS headers:** for example `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, `JMSDestination`.
- **Message properties:** metadata set by the application/provider, for example `eventType`, `tenantId`, `priorityLevel`.
- **Body:** the actual business content such as an order ID, JSON string, binary data, or structured object.

When using Spring Framework, `@JmsListener` allows a method to receive **the converted body as a Java value** without having to manually open a JMS session and call `TextMessage.getText()`.

Simple example:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @JmsListener(destination = "orders.incoming")
    public void receive(String orderId) {
        System.out.println("ORDER=" + orderId);
    }
}
~~~

If a producer sends a `TextMessage` containing `"order-42"`, with an appropriate converter, Spring invokes `receive("order-42")` and the method prints:

~~~text
ORDER=order-42
~~~

In this example, the `String orderId` parameter is the **payload parameter**, even without the `@Payload` annotation. Spring recognizes it because `String` does not belong to the special parameter types that an endpoint can inject.

It can be written more explicitly:

~~~java
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "orders.incoming")
public void receive(@Payload String orderId) {
    System.out.println("ORDER=" + orderId);
}
~~~

Both versions have the same meaning in the simple case: using the body of the JMS message after conversion. `@Payload` clarifies intent and enables integration with capabilities such as validation. **It does not automatically turn a DTO into JSON, choose a destination, or replace a MessageConverter.**

This lesson focuses on **listener data**, specifically how Spring decides which parameter receives the payload, how `@Payload` works with `@Header`/`@Headers`, Java data types after conversion, validation, Java 17+ examples, and common mistakes.

## 2. Architecture: JMS Message → Spring Messaging Message → method argument

When `@JmsListener` is active, Spring creates a message listener container, receives the JMS message from the broker, and uses a listener adapter/method argument resolvers to invoke the method. A practical view:

~~~text
Producer Java
    |
    | JmsTemplate.convertAndSend(...)
    v
JMS Queue / Topic on broker
    |
    v
JMS listener container
    |
    | receives jakarta.jms.Message
    v
Spring Messaging adapter / message conversion
    |
    +--> payload: String, byte[], Map, DTO ...
    |
    +--> mapped headers: JMS headers + application properties
    |
    v
@JmsListener method:
    onMessage(
        @Payload String body,
        @Header("eventType") String type
    )
    |
    v
Business logic
~~~

It is important to distinguish **two conversion layers** that may be involved:

1. **JMS message conversion:** `org.springframework.jms.support.converter.MessageConverter` converts between a Java object and `jakarta.jms.Message`. The default converter is typically `SimpleMessageConverter`.
2. **Spring Messaging argument resolution/conversion:** the listener method is invoked via an adapter, with `org.springframework.messaging.Message<?>`, resolvers for `@Payload`, `@Header`, `@Headers`, and optional validation. Some cases require an appropriately configured converter on the listener adapter/handler.

The fact that a producer sends a valid `TextMessage` **does not guarantee** that any arbitrary Java class can be bound to a `@Payload` parameter. The parameter type must match the object returned by the converter, or another conversion must be available to convert it to the target type.

### 2.1. Payload Is Not Synonymous with the Entire Message

A payload `"order-42"` does not automatically contain all headers, properties, and destination. If the listener needs both the order ID and `eventType`, it should receive the payload **and** the header separately:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "orders.incoming")
public void receive(
        @Payload String orderId,
        @Header("eventType") String eventType) {

    System.out.println(orderId + " / " + eventType);
}
~~~

Here `orderId` belongs to the **body**, while `eventType` belongs to **message properties mapped to Spring headers**. If the message is missing the required `eventType` header, method argument resolution may fail before executing the method body.

## 3. Importing the Correct @Payload Annotation

The annotation used with `@JmsListener` comes from **Spring Messaging**:

~~~java
import org.springframework.messaging.handler.annotation.Payload;
~~~

There is no standard `@Payload` annotation in the `jakarta.jms` package. Spring JMS relies on Spring Messaging's method-argument resolution mechanism, so this same Spring annotation can also appear in several other types of messaging endpoints.

Illustrative code:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @JmsListener(destination = "payments.incoming")
    public void receive(@Payload String paymentId) {
        System.out.println("PAYMENT=" + paymentId);
    }
}
~~~

**Import note:** do not confuse `org.springframework.jms.annotation.JmsListener` with Spring Kafka/Rabbit annotations. In Spring Boot 3.x, the JMS API types are `jakarta.jms.Message`, `jakarta.jms.Session`; the `@Payload`, `@Header`, and `@Headers` annotations still belong to `org.springframework.messaging.handler.annotation`.

### 3.1. @Payload Is Optional for Ordinary Business Parameters

Spring Framework allows:

~~~java
@JmsListener(destination = "payments.incoming")
public void receive(String paymentId) { ... }
~~~

A parameter that is not recognized as a raw `jakarta.jms.Message`, `jakarta.jms.Session`, or Spring `Message<?>` and has no header annotation is normally treated as the **payload**.

The clearest style in a method with multiple parameters:

~~~java
@JmsListener(destination = "payments.incoming")
public void receive(
        @Payload String paymentId,
        @Header("sourceSystem") String sourceSystem) {
    // Business processing...
}
~~~

The code above is a **method snippet**, which must reside in a Spring-managed component with appropriate imports. Functionality does not change just because `@Payload` is present; the main benefits are **readable intent** and reducing confusion with header metadata.

### 3.2. A Method Should Not Have Multiple Independent Payload Parameters

Avoid this design:

~~~java
// Do not expect Spring to split a single TextMessage into these two parameters.
@JmsListener(destination = "orders.incoming")
public void receive(@Payload String orderId, @Payload int quantity) {
    // ...
}
~~~

A JMS message has one body; `@Payload` does not automatically split a String into two different fields. For structured data, create a DTO/record containing the fields, or receive a JSON string and parse it intentionally. If multiple pieces of information are needed, use one payload parameter and supported header/session parameters.

## 4. Valid Parameter Types for @JmsListener

Spring Framework supports several method signature styles. Notable differences:

| Parameter | What Spring passes in | Suitable when |
| --- | --- | --- |
| `String body` | Converted payload, without needing `@Payload` | TextMessage with String content |
| `@Payload String body` | String payload, explicit intent | Readability, combining with headers/validation |
| `@Payload byte[] bytes` | Binary payload if supported by converter | BytesMessage |
| `@Payload Map<String,Object> data` | Map payload if the JMS message converter supports MapMessage | Body with multiple simple fields |
| `@Payload OrderCreated dto` | DTO, requires appropriate converter/type mapping | JSON/schema-based business payload |
| `@Header("eventType") String type` | A single Spring message header | Metadata mapped from a JMS property |
| `@Headers Map<String,Object> headers` | Collection of Spring message headers | Inspecting multiple headers |
| `jakarta.jms.Message raw` | Raw JMS message | Need native headers, properties, body |
| `jakarta.jms.TextMessage rawText` | Raw JMS TextMessage when message type matches | Using JMS-specific API directly |
| `jakarta.jms.Session session` | JMS session associated with receiving | Additional JMS operations, manual reply |
| `org.springframework.messaging.Message<T> message` | Spring Messaging message with payload and headers | Wanting a transport-independent abstraction |

**The two `Message` types are completely different:**

~~~java
jakarta.jms.Message nativeMessage;
org.springframework.messaging.Message<String> springMessage;
~~~

These are **two sample declarations**, not two initialized variables. The first type is from the JMS API and has `getJMSCorrelationID()`, `getStringProperty(...)`. The second type is a Spring abstraction and has `getPayload()`, `getHeaders()`.

**Do not** apply `@Payload` to a raw `jakarta.jms.Message` parameter and expect Spring to pass the raw JMS message as the payload. A raw JMS Message is a dedicated special parameter type; it differs from the converted Java value.

### 4.1. When to Choose a Raw Message?

If you need to process both the payload and `JMSMessageID`/`JMSReplyTo` or JMS properties that are not mapped by configuration:

~~~java
@JmsListener(destination = "orders.raw")
public void receive(jakarta.jms.TextMessage message)
        throws jakarta.jms.JMSException {

    String body = message.getText();
    String correlationId = message.getJMSCorrelationID();
    String type = message.getStringProperty("eventType");

    System.out.println(body + " / " + type + " / " + correlationId);
}
~~~

This method snippet needs to be placed in a Spring-managed bean and is only suitable for **TextMessage**. If the broker delivers a BytesMessage/MapMessage, the parameter type does not match; use `jakarta.jms.Message` and check `instanceof`, or design the destination with a clear schema.

If you only need a String business payload, receiving `@Payload String` is simpler and less coupled to JMS.

## 5. Which Payload Types Are Supported by the Default Converter?

With Spring JMS's `SimpleMessageConverter`, the common pairs are:

| Received JMS message | Java object after converter | Typical payload parameter |
| --- | --- | --- |
| `TextMessage` | `String` | `@Payload String` |
| `BytesMessage` | `byte[]` | `@Payload byte[]` |
| `MapMessage` | `Map<String,Object>` | `@Payload Map<String,Object>` |
| `ObjectMessage` | Deserialized Java Serializable object | Compatible Java type, if allowed by deserialization policy |

These conversions depend on the actual converter of the listener container. The Java 17+ examples later use **String**, `byte[]`, and `Map` so no custom converter is needed.

### 5.1. String and TextMessage

Producer:

~~~java
jmsTemplate.convertAndSend("demo.payload.text", "order-42");
~~~

Consumer:

~~~java
@JmsListener(destination = "demo.payload.text")
public void receive(@Payload String orderId) {
    System.out.println("TEXT=" + orderId);
}
~~~

When that message is delivered and the converter runs, the body `"order-42"` becomes a Java `String`.

A String containing `"{\"orderId\":\"A42\"}"` is still a String. **The `@Payload OrderDto` annotation does not automatically parse JSON** without an appropriate JSON converter.

### 5.2. byte[] and BytesMessage

Producer:

~~~java
jmsTemplate.convertAndSend("demo.payload.binary",
        new byte[] {1, 2, 3});
~~~

Consumer:

~~~java
import java.util.Arrays;

@JmsListener(destination = "demo.payload.binary")
public void receive(@Payload byte[] bytes) {
    System.out.println("BYTES=" + Arrays.toString(bytes));
}
~~~

The received payload is **raw bytes**. Spring does not automatically know whether it is UTF-8 text, an image, Avro, Protobuf, or a ZIP file. Decoding according to charset/schema is the responsibility of the application contract.

### 5.3. Map and MapMessage

Producer:

~~~java
Map<String, Object> values = new java.util.LinkedHashMap<>();
values.put("orderId", "A42");
values.put("quantity", 3);

jmsTemplate.convertAndSend("demo.payload.map", values);
~~~

Consumer:

~~~java
@JmsListener(destination = "demo.payload.map")
public void receive(@Payload Map<String, Object> values) {
    System.out.println(values.get("orderId"));
}
~~~

Both blocks are **snippets** requiring `import java.util.Map` and appropriate bean variables. For `MapMessage`, Map values must belong to the types supported by JMS MapMessage (primitives/wrappers, String, appropriate byte[]). Do not arbitrarily put `Instant`, `List`, or nested DTOs into a MapMessage and expect the converter to deep-serialize them.

### 5.4. Serializable and ObjectMessage

If a producer sends a Serializable object outside the three groups above, `SimpleMessageConverter` may create an `ObjectMessage`. The consumer receives the deserialized object when the classpath and provider trust policy match.

Example of a Java `record`:

~~~java
import java.io.Serial;
import java.io.Serializable;

public record OrderNotice(String orderId)
        implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

This is code for a standalone `OrderNotice.java` file; a record is not automatically Serializable unless declared. If an ObjectMessage containing `OrderNotice` is received and deserialization succeeds, a parameter of type `@Payload OrderNotice notice` can be bound.

**Warning:** ObjectMessage uses Java serialization, which carries deserialization risks from untrusted sources and depends on classes/versions/trusted packages. Prefer JSON or a schema-based binary format with controlled type mapping when communicating across multiple services, especially cross-language ones.

## 6. Combining @Payload with @Header and @Headers

Commonly, a business method needs the body and some metadata for routing or logging.

### 6.1. @Header for Individual Properties

Producer sets a String property:

~~~java
jmsTemplate.convertAndSend(
        "demo.orders",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            return message;
        });
~~~

Listener:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "demo.orders")
public void receive(
        @Payload String orderId,
        @Header("eventType") String eventType) {

    System.out.println("ORDER=" + orderId);
    System.out.println("EVENT=" + eventType);
}
~~~

With the default JMS header mapper, the application property `eventType` is placed into Spring message headers so the `@Header("eventType")` resolver can extract it.

Distinguish between:

- `@Payload String orderId`: extracts the body.
- `@Header("eventType") String eventType`: extracts a header mapped from a JMS property.
- JMS selector `eventType = 'ORDER_CREATED'`: uses that same property **at the provider**, before invoking the listener, if the listener configures a selector.

A missing header can cause `@Header` with `required=true` (the default) to fail during argument resolution. You can use:

~~~java
@Header(name = "sourceSystem", required = false)
String sourceSystem
~~~

This is a **parameter snippet** to be placed inside a method. When the header is absent, it may receive `null` if the parameter type allows it; the application must then handle the fallback. Do not use primitive `int` for a header that may be absent without a valid default or conversion.

### 6.2. @Headers for Multiple Headers

To inspect the set of headers mapped to Spring Messaging:

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "demo.orders")
public void receive(
        @Payload String orderId,
        @Headers Map<String, Object> headers) {

    System.out.println("ORDER=" + orderId);
    System.out.println("HAS_EVENT=" + headers.containsKey("eventType"));
}
~~~

A parameter annotated with `@Headers` must be compatible with `Map`. Do not confuse it with `@Payload Map<String,Object>`:

- `@Headers Map<...>` = **metadata headers** of Spring Messaging.
- `@Payload Map<...>` = **body** processed by the converter, e.g., MapMessage.

The two Maps may share overlapping keys, but their origin and meaning are different. Do not assume every JMS header or provider-specific property is mapped into headers: behavior depends on the `JmsHeaderMapper` and converters/adapters used.

### 6.3. Standard JMS Headers with JmsHeaders

Spring provides `org.springframework.jms.support.JmsHeaders` for standard names in the Spring Messaging abstraction.

~~~java
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(destination = "demo.orders")
public void receive(
        @Payload String body,
        @Header(JmsHeaders.CORRELATION_ID) String correlationId) {

    System.out.println("CORR=" + correlationId);
}
~~~

The Spring header named by `JmsHeaders.CORRELATION_ID` corresponds to native `JMSCorrelationID`, if provided by the provider/mapper. Use the constant instead of mistyping `"JMSCorrelationID"`, because **header names in Spring Messaging do not necessarily match JMS API field names**.

Producers should set the native correlation header using:

~~~java
message.setJMSCorrelationID("corr-42");
~~~

This is a JMS `Message` snippet before sending; **do not** use `setStringProperty("JMSCorrelationID", "corr-42")` to replace the native header.

## 7. Complete Java 17+ Example Using Spring Boot and Artemis

The example illustrates three binding styles in one small application:

1. `@Payload String` combined with `@Header("eventType")` and mapped native `JMSCorrelationID`.
2. `String` **without** `@Payload`, yet still interpreted as the payload.
3. `@Payload byte[]`, testing the payload of a BytesMessage.
4. `@Payload Map<String,Object>`, testing a MapMessage.

Each listener uses **its own dedicated queue** to avoid competing consumers and mixed message types. This is an intentional testing approach, not a requirement to always separate queues by payload type in production.

### 7.1. Environment Prerequisites

Create a Maven project on [Spring Initializr](https://start.spring.io/) with:

- Group `com.example`; Artifact `jms-payload-demo`; Java **17+**; Spring Boot **3.x**.
- Dependency **Spring for Apache ActiveMQ Artemis** (artifact `org.springframework.boot:spring-boot-starter-artemis`).
- An **out-of-process Apache ActiveMQ Artemis** broker running at `tcp://localhost:61616`.
- An account with permissions to connect/send/consume and four queues provisioned or auto-creation enabled on the broker: `demo.payload.explicit`, `demo.payload.implicit`, `demo.payload.binary`, `demo.payload.map`.
- For clear observation, initially the four queues have no backlog messages and no other consumers reading these queues.

Set the `ARTEMIS_USER` and `ARTEMIS_PASSWORD` environment variables according to your broker credentials. Do not commit real passwords to Git.

File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
~~~

`mode=native` **does not start an embedded broker**. Spring Boot with the Artemis starter and valid auto-configuration will create `ConnectionFactory`, `JmsTemplate`, and the listener infrastructure. According to Spring Boot, you generally **do not need** to manually add `@EnableJms` in a Boot application that already has complete JMS infrastructure.

### 7.2. Complete Java File

File `src/main/java/com/example/JmsPayloadDemoApplication.java`:

~~~java
package com.example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsPayloadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsPayloadDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            template.convertAndSend(
                    "demo.payload.explicit",
                    "order-42",
                    message -> {
                        message.setStringProperty(
                                "eventType", "ORDER_CREATED");
                        message.setJMSCorrelationID("corr-order-42");
                        return message;
                    });

            template.convertAndSend(
                    "demo.payload.implicit", "invoice-17");

            template.convertAndSend(
                    "demo.payload.binary", new byte[] {1, 2, 3});

            Map<String, Object> values = new LinkedHashMap<>();
            values.put("orderId", "A42");
            values.put("quantity", 3);
            template.convertAndSend("demo.payload.map", values);

            System.out.println("SENT=4");
        };
    }
}

@Component
class PayloadListeners {

    // Explicitly place @Payload, adding a property and JMS header.
    @JmsListener(destination = "demo.payload.explicit")
    public void explicit(
            @Payload String orderId,
            @Header("eventType") String eventType,
            @Header(JmsHeaders.CORRELATION_ID) String correlationId) {

        System.out.println("EXPLICIT_PAYLOAD=" + orderId);
        System.out.println("EXPLICIT_EVENT=" + eventType);
        System.out.println("EXPLICIT_CORRELATION=" + correlationId);
    }

    // A String without an annotation is still interpreted as the payload.
    @JmsListener(destination = "demo.payload.implicit")
    public void implicit(String invoiceId) {
        System.out.println("IMPLICIT_PAYLOAD=" + invoiceId);
    }

    @JmsListener(destination = "demo.payload.binary")
    public void binary(@Payload byte[] data) {
        System.out.println(
                "BINARY_PAYLOAD=" + Arrays.toString(data));
    }

    @JmsListener(destination = "demo.payload.map")
    public void map(@Payload Map<String, Object> data) {
        System.out.println("MAP_ORDER=" + data.get("orderId"));
        System.out.println("MAP_QUANTITY=" + data.get("quantity"));
    }
}
~~~

**Java structure check:** The file has one `public class JmsPayloadDemoApplication` matching the file name and a package-private class `PayloadListeners` annotated with `@Component` in a package scanned by Spring. Java 17 supports the syntax used in the example.

**JMS check:** The two calls `convertAndSend(..., "order-42")` and `convertAndSend(..., "invoice-17")` create `TextMessage` instances with the default converter. The primitive `byte[]` array creates a `BytesMessage`. A Java Map with String keys and compatible String/int values creates a `MapMessage`.

**Argument mapping check:** `@Payload String` extracts the body, `@Header("eventType")` extracts the mapped property, `@Header(JmsHeaders.CORRELATION_ID)` extracts the mapped native JMS correlation ID. Another listener uses an implicit String parameter. The last two listeners use `byte[]` and `Map`. If you have customized the JMS converter or header mapper in your project, re-verify the contract before applying the example as-is.

### 7.3. Running with Maven

In the project root directory:

~~~bash
mvn spring-boot:run
~~~

With Maven Wrapper if the project generated `mvnw.cmd` on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

When the broker, credentials, destinations, message conversion, and listener containers are all configured properly, with no stale messages or competing consumers, the **expected business lines** are:

~~~text
EXPLICIT_PAYLOAD=order-42
EXPLICIT_EVENT=ORDER_CREATED
EXPLICIT_CORRELATION=corr-order-42
IMPLICIT_PAYLOAD=invoice-17
BINARY_PAYLOAD=[1, 2, 3]
MAP_ORDER=A42
MAP_QUANTITY=3
SENT=4
~~~

This is the **set of expected lines, not a mandatory stdout order**. Spring Boot prints startup logs. `SENT=4` may appear before or after listener output because receiving is asynchronous. Lines printed **within the same method** keep the order in the code; different listeners may interleave. If there are backlogged messages or other consumers, the output may differ.

If the broker is not running, credentials are wrong, or queue permissions are missing, the application may fail on connection/initialization or sending/receiving. Do not treat this example as a self-contained broker; the infrastructure must be prepared externally.

### 7.4. Why Does the Example Show @Payload Is Optional?

The two methods:

~~~java
public void explicit(@Payload String orderId, ... ) { ... }
public void implicit(String invoiceId) { ... }
~~~

both receive a String body. The first method demonstrates the explicit annotation and header integration; the second proves that **a parameter not belonging to a special type is treated as the payload by default**.

In long code or listeners with multiple parameters, `@Payload` makes intent clear; in a simple listener with one String parameter, omitting the annotation is valid and commonly used.

## 8. DTO/record Payloads and JSON: Need a Converter, Not Just an Annotation

A common mistake is writing:

~~~java
@JmsListener(destination = "orders.json")
public void receive(@Payload OrderCreated order) {
    // ...
}
~~~

and assuming Spring will automatically parse any JSON `TextMessage` into `OrderCreated`. **That is false if no converter is configured**.

With `SimpleMessageConverter`, a `TextMessage` usually becomes a `String`. To receive a DTO from JSON, explicit JSON/String → Java type mapping is required. Spring JMS 6.x has `MappingJackson2MessageConverter`, but you must provide the Jackson dependency, target JMS message type, type-id or safe mapping, and configure the converter on the listener container actually in use.

### 8.1. Example DTO/record

File `src/main/java/com/example/OrderCreated.java`:

~~~java
package com.example;

public record OrderCreated(
        String orderId,
        int quantity) {
}
~~~

This is a valid Java 17 record, **no need to implement Serializable if using a JSON TextMessage**. It is only a model; it does not create a JMS converter on its own.

### 8.2. Configuring a JSON Converter in Spring Framework 6.x

An illustrative configuration:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JsonConverterConfig {

    @Bean
    MessageConverter orderJsonJmsConverter() {
        MappingJackson2MessageConverter c =
                new MappingJackson2MessageConverter();
        c.setTargetType(MessageType.TEXT);
        c.setTypeIdPropertyName("_type");
        c.setTypeIdMappings(
                Map.of("order-created", OrderCreated.class));
        return c;
    }
}
~~~

**This is a configuration snippet, not a full project**; Spring JMS, Jackson, and the actual `OrderCreated` class must be present. The Type-ID property `_type` is metadata that must be agreed upon between producer and consumer; JSON data in the body alone is not enough to infer the Java class if the converter relies on type-id.

To ensure the listener uses that converter in **plain Spring Framework**, you can configure a factory and specify it on the annotation:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MessageConverter;

@Configuration
class JsonListenerConfig {

    @Bean("jsonListenerFactory")
    DefaultJmsListenerContainerFactory jsonListenerFactory(
            ConnectionFactory connectionFactory,
            MessageConverter orderJsonJmsConverter) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(orderJsonJmsConverter);
        return factory;
    }
}
~~~

Listener selects the factory:

~~~java
@JmsListener(
        destination = "orders.json",
        containerFactory = "jsonListenerFactory")
public void receive(@Payload OrderCreated order) {
    System.out.println(order.orderId());
}
~~~

This is a combined configuration example, **not standalone runnable code**, because it still needs a `ConnectionFactory` bean, `@JmsListener` registration (in plain Spring: `@EnableJms`), and a producer using a compatible JSON converter/schema. In Spring Boot, automatic binding of a `MessageConverter` bean also depends on configuration and version; verify what the factory actually receives instead of merely assuming every listener automatically uses every converter bean.

### 8.3. Separating Conversion Failures and Binding Failures

A message containing invalid JSON can fail **before the listener method is invoked**. Even if JSON parsing succeeds, the body structure may be incompatible with `OrderCreated`, or the type id may be missing/wrong/rejected by trust mapping. Therefore, the absence of logs inside the method **does not prove the queue is empty**.

Do not build type mapping by arbitrarily trusting any class name present in the message; only map to the set of domain types permitted by the application. This is an important security boundary when deserializing data from a messaging system.

## 9. Validation with @Valid @Payload

`@Payload` can be combined with Bean Validation to validate the object **after conversion**, before the listener's business logic runs.

DTO file with constraints:

~~~java
package com.example;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record OrderCreated(
        @NotBlank String orderId,
        @Min(1) int quantity) {
}
~~~

Listener:

~~~java
import jakarta.validation.Valid;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;

@JmsListener(
        destination = "orders.validated",
        containerFactory = "jsonListenerFactory")
public void handle(@Valid @Payload OrderCreated order) {
    System.out.println("VALID_ORDER=" + order.orderId());
}
~~~

**Prerequisites:** Jakarta Validation API/provider available (e.g., adding `spring-boot-starter-validation`), a working JSON converter, and a `Validator` properly configured for handler argument resolution. Merely adding `@Valid` without validator/messaging handler configuration does not guarantee validation will be triggered in every setup.

In plain Spring Framework, the official documentation illustrates a `DefaultMessageHandlerMethodFactory` supplied with a validator via `JmsListenerConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

@Configuration
@EnableJms
class JmsValidationConfig implements JmsListenerConfigurer {

    private final Validator validator;

    JmsValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        DefaultMessageHandlerMethodFactory handlerFactory =
                new DefaultMessageHandlerMethodFactory();
        handlerFactory.setValidator(validator);
        registrar.setMessageHandlerMethodFactory(handlerFactory);
    }
}
~~~

This is a **configuration snippet** that depends on a Spring-managed `Validator` bean; JMS connection/listener factory beans still must be configured for the environment. If validation fails, an error may be thrown at the resolver/handler layer **before the method body**, and rollback/redelivery behavior depends on the listener container's session transaction/acknowledgment settings. Do not treat validation as a guarantee that a message will automatically be moved to a DLQ; retry/DLQ requires separate configuration.

### 9.1. When Is @Payload(required = false) Used?

`@Payload` has a `required` attribute, which defaults to `true`. You can declare:

~~~java
public void receive(@Payload(required = false) String value) {
    // Handle if conversion provides an empty/null payload.
}
~~~

This is an **illustrative method snippet**, not a complete listener. When `required=false`, the resolver does not enforce non-null in cases where an empty payload can be represented. However, this **does not cause the method to run when the queue is empty**, does not synthesize a fake JMS message, and does not guarantee that any null JMS Message body can be handled by the converter/adapter. If the business contract requires a body, keep `required=true` and validate explicitly.

Do not use `@Payload(required=false)` to "ignore JSON conversion errors": malformed JSON is still a conversion/schema error, not a valid absent payload.

## 10. Receiving Spring Message<T> When Both Payload and Headers Are Needed

If the code wants to wrap both payload and metadata in an abstraction not directly coupled to JMS:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.Message;

@JmsListener(destination = "orders.incoming")
public void receive(Message<String> message) {
    String body = message.getPayload();
    Object eventType = message.getHeaders().get("eventType");

    System.out.println("BODY=" + body);
    System.out.println("EVENT_TYPE=" + eventType);
}
~~~

This is a Spring-managed listener method snippet. Note that `org.springframework.messaging.Message<String>` is **not** `jakarta.jms.Message`.

Advantages:

- Keeps payload and headers in a single value.
- Easy to unit-test business logic against the messaging abstraction.
- No need to call JMS API getters when only mapped metadata is required.

Limitations:

- Header mapping behavior depends on the `JmsHeaderMapper`/converter in use.
- If a native `JMSReplyTo` object or provider-specific feature is needed, a raw JMS Message may be more suitable.
- `Message<T>` has a type parameter, but it does not prove the runtime payload is guaranteed to be `T` if conversion is misconfigured; errors may arise when the resolver/converter invokes the method.

### 10.1. @Header and MessageHeaders Differ

The same method can extract a single header or all headers:

~~~java
@JmsListener(destination = "orders.incoming")
public void receive(
        @Payload String body,
        @Header("eventType") String eventType,
        @Headers Map<String, Object> allHeaders) {

    // ...
}
~~~

Use `@Header` when you only care about one field; use `@Headers Map` when you genuinely need multiple metadata entries. Do not blindly log all headers in production because some systems may place sensitive data in properties.

## 11. Other Payload Forms: Boolean, Integer, POJO, and Collections

A common trap: not every Java type maps to its own dedicated JMS Message type.

- `String` usually creates a TextMessage.
- `byte[]` usually creates a BytesMessage.
- `Map` with valid values usually creates a MapMessage.
- `Serializable` objects outside the branches above may create an ObjectMessage.
- `Integer` and `Boolean` implement Serializable so they can travel via ObjectMessage with `SimpleMessageConverter`; there is **no** standard JMS `IntegerMessage`/`BooleanMessage`.
- `List` is not equivalent to `MapMessage`. A Serializable implementation may be handled via ObjectMessage, but there is no ListMessage by default.
- Java `record` types do not automatically implement Serializable; to receive JSON DTOs, use a custom JSON converter.

Illustrative example:

~~~java
// If the template uses SimpleMessageConverter and the provider allows ObjectMessage:
jmsTemplate.convertAndSend("orders.number", Integer.valueOf(42));
~~~

Listener receiving the matching object:

~~~java
@JmsListener(destination = "orders.number")
public void receive(@Payload Integer number) {
    System.out.println("NUMBER=" + number);
}
~~~

However, **ObjectMessage carries Java deserialization risks** and may be blocked by provider/trust policies. Do not design inter-service communication with ObjectMessage by default if you can use TextMessage JSON or a BytesMessage schema with safe type mapping.

### 11.1. When Will a Method Receiving a DTO Work?

There are two distinct scenarios:

1. A JMS ObjectMessage actually contains a compatible Serializable object and policy permits deserialization: the Java payload can be the DTO directly.
2. A JMS TextMessage contains JSON: a JSON converter or dedicated parsing is required. `@Payload MyDto` does not do that on its own.

Some applications configure an additional Spring Messaging conversion service to convert one simple type to another. However, **a conversion service does not replace a general-purpose schema decoder**. Do not infer that Map, JSON text, or byte[] can always be converted into an arbitrary DTO.

## 12. Unit and Integration Testing for @Payload

### 12.1. Unit-Testing Business Logic Independently of JMS

One advantage of receiving a Java payload is that business methods are easy to test in plain Java:

~~~java
public class OrderService {

    public String normalize(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId required");
        }
        return orderId.trim();
    }
}
~~~

This is a plain Java class; you can test it without a broker. The listener acts only as an adapter receiving the message and calling the service:

~~~java
@JmsListener(destination = "orders.incoming")
public void handle(@Payload String orderId) {
    String normalized = orderService.normalize(orderId);
    System.out.println(normalized);
}
~~~

The listener snippet requires an `orderService` bean/injected field; **it is not a standalone Java file**. Separating business logic this way allows testing payload validation/processing independently of the listener container.

### 12.2. Integration Tests Must Verify the Actual Converter

A unit test calling `handle("order-42")` directly **does not verify** whether the JMS broker can convert a TextMessage into a String or map properties into `@Header`. Integration tests require a real broker or compatible test infrastructure, sending messages and confirming the listener is invoked.

Checklist:

1. Send a TextMessage with a String body; verify `@Payload String` receives it properly.
2. Send a BytesMessage; verify `@Payload byte[]` is not automatically decoded into a String.
3. Send a MapMessage; verify `@Payload Map` has keys/values of the expected types.
4. Send a JSON TextMessage without configuring a JSON converter; do not expect `@Payload OrderCreated` to work.
5. Enable the JSON converter and safe type-id mapping; verify the DTO method is invoked.
6. Omit the `eventType` property; confirm `@Header(required=true)` raises an error in the pipeline.
7. Send a DTO violating `@Valid` when a validator is present; check error handling/redelivery policy.
8. Verify that message conversion exceptions occur **before the business method**, rather than only catching exceptions inside the method.
9. Check queue depth, listener consumer count, and DLQ to see how failed messages were handled.
10. Run tests on clean queues or use unique IDs; avoid stale messages and multiple consumers causing flaky results.

### 12.3. Do Not Confuse @Payload with a JMS Selector

A listener:

~~~java
@JmsListener(
        destination = "orders.incoming",
        selector = "eventType = 'ORDER_CREATED'")
public void receive(@Payload String body) {
    // ...
}
~~~

has two separate responsibilities:

- **`selector`** operates on the consumer/JMS provider and decides **which messages are delivered**.
- **`@Payload`** operates in the listener argument resolver and decides **which method argument receives the body data**.

`@Payload` cannot replace a selector and vice versa. A selector can only read application properties and standard headers permitted by JMS; it cannot directly read a JSON body.

## 13. Common Errors When Receiving Payloads

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `@Payload String` listener is not invoked | Endpoint not registered, wrong destination/queue, broker disconnected, or converter/selector error | Check listener infrastructure, broker metrics, queue, exception logs |
| `@Payload OrderCreated` does not receive JSON TextMessage | Converter/type mapping not configured | Use an appropriate JSON converter, align schema/metadata |
| `@Header("eventType")` reports missing header | Producer did not set property, typo, or mapper ignored it | Set property with exact name/type, inspect mapper |
| `@Headers Map` contains more headers than expected | Spring maps both standard JMS headers and application properties | Use only needed keys, do not treat it as a payload Map |
| `@Payload byte[]` receives binary but code treats it as String | Not decoded with charset/codec | Choose explicit schema/codec/charset |
| `@Payload Map` has values with unexpected types | MapMessage body has primitive wrappers; schema drift | Check contract and runtime type of each entry |
| `ObjectMessage` deserialization rejected | Trusted packages/classpath/serialVersionUID/security policy | Check provider restrictions, avoid trust-all, consider JSON |
| Method `receive(String, String)` is misinterpreted | Both parameters are usually treated as payloads, does not auto-split body | Use one `@Payload` and one `@Header`, or a DTO |
| Wrong `Message` import | Confusing `jakarta.jms.Message` with `org.springframework.messaging.Message<T>` | Use fully qualified class names when code is ambiguous |
| DTO validation does not run | Missing Jakarta Validator or handler method factory wiring | Configure provider/validator and verify with integration test |
| Conversion error occurs but no log appears inside method | Error occurs before the method is invoked | Check listener container error logs and DLQ |
| Using `@Payload(required=false)` thinking an empty queue will call the method | The annotation does not synthesize messages | Use polling/timeout if you need to detect an empty queue |
| Payload is read properly but JMSCorrelationID is lost | Only receiving the Java value, not metadata | Use `@Header(JmsHeaders.CORRELATION_ID)` or raw Message |
| Message appears to be processed multiple times | Rollback/redelivery, multiple consumers/attempts | Check session transactions, idempotency, DLQ |
| System uses `javax.jms.*` with Boot 3 | API incompatible with Jakarta JMS | Use Jakarta Messaging dependencies/provider client |

### 13.1. Distinguishing Conversion Failure from Business Failure

Errors **before entering the method** typically occur at:

~~~text
Incoming JMS message
     |
     v
JMS MessageConverter
     |
     v
Spring argument resolver
     |
     +--> payload type mismatch?
     +--> required @Header missing?
     +--> @Valid rejects DTO?
     |
     v
Listener method is invoked
     |
     +--> business validation / database / API / logic exception
~~~

When your code fails to print a log line placed at the very start of the listener method, do not immediately conclude there are no messages. Check listener registration, broker queue, selector, converter, header mapping, and validation error logs.

### 13.2. Notes on Transactions, Retries, and DLQ

`@Payload` does not alter JMS acknowledgment or transactions. If conversion/validation fails, whether the message is redelivered depends on `DefaultJmsListenerContainerFactory`, session transactions, the provider, and how error handlers/rollbacks are configured.

For production systems, consider:

- Enabling session transactions matching reliability requirements.
- Applying idempotency to business operations that may receive duplicate messages.
- Limiting retry counts and monitoring the dead-letter queue for poison messages.
- Logging sufficient ID/correlation/type details for debugging without logging raw payloads containing sensitive data.
- Not treating `@Valid` or converters as substitutes for authentication/authorization.
- When using a database and JMS together, a local JMS session transaction does not automatically create an atomic two-system transaction; use outbox/inbox patterns or transaction coordination when needed.

## 14. How to Choose a Practical Listener Signature

| Requirement | Recommended signature | Reason |
| --- | --- | --- |
| Only need a String order ID | `handle(@Payload String orderId)` | Concise, clearly expresses payload |
| Only a single simple String parameter | `handle(String orderId)` | `@Payload` can be omitted |
| Body and one required property | `handle(@Payload String body, @Header("eventType") String type)` | Separates body and metadata |
| Body and an optional property | `handle(@Payload String body, @Header(name="traceId", required=false) String trace)` | Handles optional header |
| Body and multiple headers | `handle(@Payload String body, @Headers Map<String,Object> headers)` | Accesses the header map |
| Need native JMS fields/Session | `handle(jakarta.jms.Message raw, jakarta.jms.Session session)` | Direct use of JMS API |
| Want a transport-independent envelope | `handle(org.springframework.messaging.Message<String> message)` | Payload and headers in one object |
| Need a JSON business DTO | `handle(@Valid @Payload OrderCreated dto)` | Requires proper JSON converter and validator |
| Receiving a BytesMessage | `handle(@Payload byte[] bytes)` | Binary payload per contract |
| Receiving a MapMessage | `handle(@Payload Map<String,Object> map)` | Map payload with clear schema |

**Guideline:** prefer signatures that **receive only what the business logic needs**. If a service only needs `orderId`, do not force it to depend on the entire `jakarta.jms.Message`. If a correlation header is needed, receive it via `@Header` or raw Message instead of trying to embed it in a String payload.

When the codebase has many listeners and converters, explicitly define destinations, type mappings, schema versions, error policies, and transactions. Adding `@Payload` alone does not resolve those parameters.

## 15. Self-Check Questions

**Question 1.** Does `@JmsListener(destination="orders") public void receive(String value)` require `@Payload` to run?

**Answer:** No. Spring treats a String business parameter that is not a special type as the payload by default.

**Question 2.** What is the difference between `@Payload String body` and `@Header("eventType") String type`?

**Answer:** The first receives the Java body after conversion; the second receives metadata from Spring headers mapped from a JMS header/property.

**Question 3.** How does `@Payload Map<String,Object> values` differ from `@Headers Map<String,Object> headers`?

**Answer:** A payload Map typically represents data from a MapMessage/body; a headers Map contains metadata. They are not interchangeable.

**Question 4.** Why doesn't a TextMessage containing JSON automatically bind to `@Payload OrderCreated`?

**Answer:** SimpleMessageConverter turns a TextMessage into a String by default, without automatically parsing JSON into an arbitrary class. A JSON converter and type mapping are required.

**Question 5.** If you want both the payload and `JMSCorrelationID`, what can you use?

**Answer:** `@Payload String` combined with `@Header(JmsHeaders.CORRELATION_ID) String`, or receive a raw `jakarta.jms.Message`.

**Question 6.** Can `@Payload` be applied to a raw `jakarta.jms.Message` to turn it into a String payload?

**Answer:** No. A raw JMS Message is a separate argument type, not a converted Java body value.

**Question 7.** Are `Byte[]` and `byte[]` treated the same when sent by `SimpleMessageConverter`?

**Answer:** No. A primitive `byte[]` array takes the BytesMessage branch; `Byte[]` does not take the same branch and may become an ObjectMessage if Serializable.

**Question 8.** What is needed to validate a DTO using `@Valid @Payload`?

**Answer:** A converter producing the right DTO, a Jakarta validation provider, and a Validator integrated into the message handler factory; ack/transaction policies handle failures separately.

**Question 9.** Does `@Payload(required=false)` cause the listener to be invoked when the queue has no messages?

**Answer:** No. It only adjusts how the resolver handles an absent payload in an actually delivered message, when supported by the pipeline.

**Question 10.** If two listener methods share the same queue, one receiving String and one receiving Map, do they automatically route by body type?

**Answer:** Do not rely on that. They are competing consumers; separate destinations, selectors/properties, or explicit routing should be used.

**Question 11.** Why is a unit test calling the listener method directly insufficient to test JMS conversion?

**Answer:** Because unit tests bypass the broker, JMS message converter, argument resolvers, header mapping, and transactions. Appropriate integration tests are needed.

**Question 12.** Once a payload is converted successfully, is it guaranteed that the message is acknowledged or the database is committed?

**Answer:** No. Delivery, transactions, retries, and business processing are separate concerns, depending on container and infrastructure configuration.

## Official References

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): `@JmsListener`, method argument types, `@Payload`, `@Header`, `@Headers`, `Message<?>`, validation.
- [Spring Framework 6.2 Javadoc — @Payload](https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html): `required` attribute, payload binding and conversion.
- [Spring Framework 6.2 Javadoc — JmsListener](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html): endpoint signature, factory, destination, selector, and lifecycle.
- [Spring Framework 6.2 Javadoc — JmsHeaders](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/jms/support/JmsHeaders.html): Spring Messaging header names corresponding to standard JMS fields.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `SimpleMessageConverter` and `MessagePostProcessor`.
- [Spring Framework 6.2 Javadoc — DefaultMessageHandlerMethodFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html): resolver and validator for annotated methods.
- [Spring Boot — Messaging with JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis, auto-configuration, `@JmsListener`.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): Spring Boot starter, producer, consumer, and converter.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS message types, standard headers, properties, queue semantics.
