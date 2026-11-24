# SimpleMessageConverter and Supported Data Types

**Topic:** Spring Framework - jms → Data Conversion

## 1. What Problem Does SimpleMessageConverter Solve?

When using the JMS API directly, an application must create a specific `jakarta.jms.Message` using `Session`, such as `TextMessage`, `BytesMessage`, `MapMessage`, or `ObjectMessage`. In Spring Framework, `JmsTemplate` provides `convertAndSend(...)` and `receiveAndConvert(...)` methods to convert between **Java values** and **JMS Messages**.

The `org.springframework.jms.support.converter.SimpleMessageConverter` class is the default conversion strategy of `JmsTemplate` when no other converter is specified. It applies simple rules based on the input Java type or input JMS message type:

- `String` ↔ `TextMessage`.
- `byte[]` ↔ `BytesMessage`.
- `java.util.Map` ↔ `MapMessage`.
- `java.io.Serializable` object ↔ `ObjectMessage`.

For example, without manually creating a `TextMessage`:

~~~java
// jmsTemplate is a valid org.springframework.jms.core.JmsTemplate bean.
jmsTemplate.convertAndSend("orders.queue", "order-42");
~~~

Spring takes the string `"order-42"`, uses the converter to create a `TextMessage`, and sends it to the destination `orders.queue`. On the receiving side, `receiveAndConvert("orders.queue")` can return a corresponding `String`.

**Important limitation:** SimpleMessageConverter **does not** automatically turn arbitrary POJOs into JSON, does not automatically convert a Java record into a `MapMessage`, and has no knowledge of the application's business schema. It dispatches based on **Java types** and standard JMS rules.

This lesson focuses on **data conversion** in Spring JMS, using Java **17+**, Spring Framework **6.x / Spring Boot 3.x** with the `jakarta.jms.*` package. Legacy systems use `javax.jms.*`; you must choose the right JMS client API for the runtime and never mix the two incompatible namespaces.

## 2. The Big Picture: Java Objects and JMS Messages

~~~text
                         PRODUCER
 Java value                              JMS message
 ─────────────────────────────────────────────────────────
 String "hello"                      ->  TextMessage
 byte[] {1,2,3}                      ->  BytesMessage
 Map<String,Object>                  ->  MapMessage
 Serializable object                 ->  ObjectMessage
          |                                    |
          |     JmsTemplate.convertAndSend     |
          +---------- SimpleMessageConverter -+
                                               |
                                           JMS provider
                                               |
                                            BROKER
                                               |
                         CONSUMER
 JMS message                            Java value
 ─────────────────────────────────────────────────────────
 TextMessage                         -> String
 BytesMessage                        -> byte[]
 MapMessage                          -> Map<String, Object>
 ObjectMessage                       -> Serializable object
          |                                    |
          +--- SimpleMessageConverter ---------+
                JmsTemplate.receiveAndConvert
~~~

| Java Value When Sending | JMS Message When Sending | Result After Receive & Convert | Key Points to Remember |
| --- | --- | --- | --- |
| `String` | `TextMessage` | `String` | Does not auto-parse JSON even if the string content looks like JSON |
| `byte[]` | `BytesMessage` | `byte[]` | Preserves raw bytes, no automatic charset |
| `Map<?, ?>` with valid keys/values | `MapMessage` | `Map<String, Object>` | Values in the Map must be body types supported by JMS |
| `Serializable` not in the three groups above | `ObjectMessage` | Deserialized object | Java serialization; must consider security and class versioning |

**Dispatch order matters:** a `HashMap` usually also implements `Serializable`, yet the converter prioritizes the **Map → MapMessage** branch. Conversely, an `ArrayList` (Serializable but not a Map) can follow the **ObjectMessage** branch, as there is no corresponding JMS `ListMessage`.

On the other hand, `Byte[]` (wrapper array, uppercase B) is **different** from `byte[]` (primitive array); it does not match the `byte[] → BytesMessage` branch. Since it is a Serializable object array, it can be handled as an ObjectMessage. Use `byte[]` when you specifically want a `BytesMessage`.

## 3. API and Where Spring Performs Conversion

Spring JMS defines the interface:

~~~java
package org.springframework.jms.support.converter;

public interface MessageConverter {
    jakarta.jms.Message toMessage(
            Object object, jakarta.jms.Session session)
            throws jakarta.jms.JMSException, MessageConversionException;

    Object fromMessage(jakarta.jms.Message message)
            throws jakarta.jms.JMSException, MessageConversionException;
}
~~~

This is an **API signature representation**, not a Java file to paste into a project (Spring's interface already exists in the dependency). Two directions:

1. **`toMessage(Object, Session)`:** Java object → JMS Message. Spring needs a `Session` to create the right message type.
2. **`fromMessage(Message)`:** JMS Message → Java object. The converter reads the message content according to the JMS type.

`JmsTemplate.convertAndSend(...)` uses `toMessage` before sending. `JmsTemplate.receiveAndConvert(...)` receives the message and then uses `fromMessage`. These operations **do not alter** queue/topic semantics, transactions, acknowledgment, or broker access permissions.

### 3.1. Where the Converter Is Not Called

~~~java
// Converts Java object to JMS Message.
jmsTemplate.convertAndSend("orders.queue", "hello");

// Converts JMS Message to Java object.
Object result = jmsTemplate.receiveAndConvert("orders.queue");

// Manually creates JMS Message; does not invoke SimpleMessageConverter.toMessage.
jmsTemplate.send("orders.queue",
        session -> session.createTextMessage("hello"));

// Receives raw JMS Message; does not invoke fromMessage.
jakarta.jms.Message raw = jmsTemplate.receive("orders.queue");
~~~

These snippets are **illustrations inside a method that already has a `jmsTemplate` bean**. Synchronous receive can block depending on the receive timeout, and `receiveAndConvert` can return `null` when the wait times out. Do not treat `null` as evidence that the converter failed.

### 3.2. The Converter Handles the Body, Not Header Mapping

A `TextMessage` can carry `JMSCorrelationID`, `JMSReplyTo`, and message properties. `SimpleMessageConverter.fromMessage` returns the **body as a Java object**, rather than turning all JMS headers/properties into a business Map.

To add headers/properties before sending, use a `MessagePostProcessor`:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setJMSCorrelationID("corr-42");
            return message;
        });
~~~

Here the converter creates the `TextMessage`, then the callback receives the **JMS Message** to add metadata before sending. Do not confuse `org.springframework.jms.core.MessagePostProcessor` with the header mapping of `org.springframework.messaging.Message<?>`.

## 4. String ↔ TextMessage

This is the simplest case. When sending a `String`:

~~~java
jmsTemplate.convertAndSend("demo.converter", "Hello JMS");
~~~

The converter creates a `TextMessage` containing text matching the exact string content. When `fromMessage` is called on a `TextMessage`, it reads `getText()` and returns a Java `String`.

Equivalent low-level API illustration:

~~~java
// session is a valid jakarta.jms.Session.
jakarta.jms.TextMessage message =
        session.createTextMessage("Hello JMS");
String text = message.getText();
System.out.println(text);
~~~

Output:

~~~text
Hello JMS
~~~

The snippet requires a JMS Session and does not run standalone without a provider/broker. However, the converter rule does not depend on string content: the string `"{\"id\":1}"` is still just **String → TextMessage**; SimpleMessageConverter does not parse it into a POJO, Map, or JSON tree.

**Common misconception:** a String containing XML or JSON does not make the message automatically carry a validated data format. It is simply bytes/text inside a TextMessage. JSON parsing/deserialization requires Jackson or a dedicated converter with explicit charset/schema and proper validation.

### 4.1. When Should You Use String?

- Logs, simple commands, or pre-serialized text payloads.
- JSON text already produced with `ObjectMapper.writeValueAsString(...)` in the application.
- When you want easy inspection via the JMS console and want to avoid Java ObjectMessage serialization.
- When producer and consumer agree on the body's encoding, format, and version.

Do not send complex objects expecting `SimpleMessageConverter` to automatically turn POJOs into JSON. If you already serialized to a String in the application, the converter only handles the **String ↔ TextMessage** layer.

## 5. byte[] ↔ BytesMessage

For binary data, pass `byte[]` to `convertAndSend`:

~~~java
byte[] payload = new byte[] {1, 2, 3, 4};
jmsTemplate.convertAndSend("demo.converter", payload);
~~~

The converter creates a `BytesMessage` and writes the four bytes sequentially. When converting back, it reads the contents of the `BytesMessage` and returns a `byte[]`.

**Unlike `ObjectMessage`:** the converter does not need Java serialization for `byte[]` in this branch; these are raw bytes. Do not assume the bytes are UTF-8, a Java serialization stream, or JSON. The consumer must know how to decode them according to the contract.

If the business payload is UTF-8 text encoded into bytes:

~~~java
import java.nio.charset.StandardCharsets;

byte[] encoded = "Hello".getBytes(StandardCharsets.UTF_8);
// Producer sends byte[] -> BytesMessage.
jmsTemplate.convertAndSend("demo.converter", encoded);

// Consumer upon receiving byte[]:
String decoded = new String(encoded, StandardCharsets.UTF_8);
~~~

This illustrates encoding/decoding with an existing byte array, not complete broker-receiving logic. In a real system, decode the **byte array returned by `receiveAndConvert`** rather than reusing the producer's array.

### 5.1. Size and Memory Considerations

When `fromMessage` reads a `BytesMessage`, the application may need to allocate a `byte[]` holding the entire payload. For very large messages, check the broker's **message size limits** and consumer-side memory. JMS is not a default large-file upload system; using object storage and sending a reference may be more appropriate.

If you want compression, encryption, or a binary schema like Avro/Protobuf, perform that in a separate step before/after SimpleMessageConverter. The default class **does not compress, encrypt, or validate schemas automatically**.

## 6. Map ↔ MapMessage: Structured Metadata in the Body

A `Map<String, Object>` with valid keys and values can be converted into a JMS `MapMessage`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Object> order = new LinkedHashMap<>();
order.put("orderId", "A42");    // String
order.put("quantity", 3);       // Integer
order.put("express", true);     // Boolean

jmsTemplate.convertAndSend("demo.converter", order);
~~~

The converter creates a `MapMessage` and sets each entry using the JMS-supported typed APIs. When converting back, it reads the entry names and returns a Java `Map`.

**Important limitation:** MapMessage **does not** store arbitrary Java objects like an in-app `Map<String, Object>`. Valid JMS body value types include boolean/byte/short/char/int/long/float/double, their corresponding wrappers, `String`, `byte[]` (and null cases per provider/spec contract). Map keys must be **String**. If the Map contains `BigDecimal`, `Instant`, `List`, or a nested `Map` as a value, conversion may fail; serialize the body to JSON or design a suitable schema instead of relying on automatic conversion.

### 6.1. MapMessage Fields vs. Message Properties

MapMessage stores entries in the **message body**:

~~~text
MapMessage:
  body:
    orderId   -> "A42"
    quantity  -> 3
    express   -> true

  properties:
    tenantId  -> "blue"
  headers:
    JMSMessageID -> ID:...
~~~

These are three distinct data layers. Having a `MapMessage` body entry `quantity=3` **does not allow a selector** `quantity >= 2` to access that field. JMS selectors read **message properties and certain standard headers**, not the body.

To let the broker filter by quantity:

~~~java
jmsTemplate.convertAndSend(
        "demo.converter",
        order,
        message -> {
            message.setIntProperty("quantity", 3);
            return message;
        });
~~~

Now there is a **body entry** `quantity=3` and a **property** `quantity=3`. Despite having the same name, they are two separate data areas. You should only copy metadata to properties when it is genuinely needed for selectors/routing, avoiding unnecessary duplication.

### 6.2. MapMessage Is Not JSON

A `MapMessage` uses the JMS native body format. It is not a `TextMessage` containing JSON like:

~~~json
{"orderId":"A42","quantity":3,"express":true}
~~~

Therefore, a consumer expecting a JSON String cannot implicitly coerce a `MapMessage` into a JSON string. When a system communicates across multiple platforms or runs HTTP/REST in parallel, consider an explicit JSON converter standard.

### 6.3. Map Element Ordering Is Not Guaranteed by Contract

In Java, `LinkedHashMap` preserves insertion order when the producer creates the object. However, `MapMessage` is a different message type and JMS does not promise that iterating over fields will preserve the original insertion order. In tests, compare **fields by key**, not enumeration order or the `Map.toString()` string on the receiving side.

## 7. Serializable ↔ ObjectMessage

If a Java object implements `java.io.Serializable` and does not fall under the String, byte[], or Map branches, SimpleMessageConverter can create a JMS `ObjectMessage`:

~~~java
// Integer implements java.io.Serializable:
jmsTemplate.convertAndSend("demo.converter", Integer.valueOf(42));
~~~

The corresponding JMS Message is an `ObjectMessage`. Upon receiving and converting, the object deserializes into an `Integer` with value 42 (assuming the provider/deserialization policy permits it).

A custom DTO must implement `Serializable` if you want to use this approach:

~~~java
import java.io.Serial;
import java.io.Serializable;

public record OrderNotice(String orderId, boolean express)
        implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

This is a **compilable Java data type in file OrderNotice.java**. To send:

~~~java
jmsTemplate.convertAndSend(
        "demo.converter",
        new OrderNotice("A42", true));
~~~

However, **you should not choose ObjectMessage by default for production or cross-service systems**. It carries several risks:

1. **Java serialization** tightly couples classes/`serialVersionUID`/serialization compatibility between producer and consumer.
2. The receiver must have the matching class on its classpath. Changing packages/classes or serialized object structure can break deserialization.
3. Deserializing untrusted data can introduce **security vulnerabilities**, especially when a provider permits deserializing arbitrary classes. Use provider allowlists/trusted packages and never accept untrusted ObjectMessages indiscriminately.
4. Brokers/providers may restrict or reject ObjectMessage under security policies.
5. A Java object is not a portable wire format for JavaScript, Python, or other systems.

### 7.1. A Record Is Not Automatically Serializable

A Java `record` does not automatically implement `Serializable` just because it is a record. For example:

~~~java
public record OrderEvent(String orderId) { }
~~~

This is a syntactically valid Java record, **but it does not automatically satisfy the Serializable branch** of SimpleMessageConverter. Calling `convertAndSend` with an object that is not a String, byte[], Map, or Serializable leaves the converter with no matching conversion rule and can throw `MessageConversionException`.

If you want JSON for DTOs/records, use a dedicated JSON converter instead of adding `implements Serializable` just to bypass a conversion error.

## 8. Complete Example: Spring Boot 3.x, Java 17+, and Artemis

This example shows **all four JMS Message types** produced when sending Java objects, and then decoded back by SimpleMessageConverter. No custom message converter bean is needed. We use a consumer accepting raw JMS Messages to observe the exact type; Spring can configure listener auto-conversion for other business parameter types in regular applications.

### 8.1. Prerequisites

- JDK 17+, Maven or Maven Wrapper.
- A Spring Boot **3.x** project with the **Spring for Apache ActiveMQ Artemis** dependency (Maven coordinate `org.springframework.boot:spring-boot-starter-artemis`). You can generate the project at [Spring Initializr](https://start.spring.io/), group `com.example`, artifact `simple-converter-demo`.
- **Out-of-process Artemis broker** running at `tcp://localhost:61616`; allowing the user/password to connect, send to, and receive from queue `demo.converter`. Provision the queue or enable auto-create per broker policy.
- The receiver environment must permit deserializing `java.lang.Integer` used in ObjectMessage. Although it is a standard Java type, some providers configured with strict allowlists may still reject ObjectMessage. Do not open up the entire trust list in production just to run an example.
- Set environment variables `ARTEMIS_USER` and `ARTEMIS_PASSWORD` to actual broker credentials.

File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`mode=native` does not start an embedded broker. The line `spring.jms.pub-sub-domain=false` selects queue semantics in the example.

File `src/main/java/com/example/SimpleConverterDemoApplication.java`:

~~~java
package com.example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;
import jakarta.jms.Message;
import jakarta.jms.ObjectMessage;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.SimpleMessageConverter;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class SimpleConverterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SimpleConverterDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            // String -> TextMessage.
            template.convertAndSend("demo.converter", "hello");

            // byte[] -> BytesMessage.
            template.convertAndSend(
                    "demo.converter", new byte[] {1, 2, 3});

            // Map<String,Object> -> MapMessage.
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("orderId", "A42");
            data.put("quantity", 3);
            template.convertAndSend("demo.converter", data);

            // Serializable Integer -> ObjectMessage.
            template.convertAndSend(
                    "demo.converter", Integer.valueOf(42));

            System.out.println("SENT=4");
        };
    }
}

@Component
class ConverterInspector {

    private final SimpleMessageConverter converter =
            new SimpleMessageConverter();

    @JmsListener(destination = "demo.converter")
    public void inspect(Message message) throws JMSException {
        Object value = converter.fromMessage(message);

        if (message instanceof TextMessage
                && value instanceof String text) {
            System.out.println("TEXT=" + text);
        } else if (message instanceof BytesMessage
                && value instanceof byte[] bytes) {
            System.out.println("BYTES=" + Arrays.toString(bytes));
        } else if (message instanceof MapMessage
                && value instanceof Map<?, ?> data) {
            System.out.println(
                    "MAP=orderId:" + data.get("orderId")
                    + ",quantity:" + data.get("quantity"));
        } else if (message instanceof ObjectMessage
                && value instanceof Integer number) {
            System.out.println("OBJECT=" + number);
        } else {
            throw new IllegalStateException(
                    "Unexpected JMS message type/payload");
        }
    }
}
~~~

**Why does this example compile?** The file contains one `public class SimpleConverterDemoApplication` matching the filename and one package-private `@Component`. It uses Java 17 pattern matching for `instanceof`. All four branches use Java and JMS types supported by SimpleMessageConverter; no separate POJO/deserialization class is needed.

### 8.2. Running with Maven

At the project root directory:

~~~bash
mvn spring-boot:run
~~~

If the project has Maven Wrapper on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With the right broker, queue, credentials, deserialization policy, and **no leftover messages from a previous run**, the business output lines on a successful run include:

~~~text
SENT=4
TEXT=hello
BYTES=[1, 2, 3]
MAP=orderId:A42,quantity:3
OBJECT=42
~~~

**The order above is for learning presentation, not a guaranteed stdout order.** Consumers receive asynchronously; `SENT=4` may appear before or after the received lines, and the order of the three/four message types also depends on how the broker and listener container dispatch them. Spring also prints startup logs. If the broker lacks the destination/permissions, or the provider rejects deserialization, errors will occur instead of all lines appearing.

### 8.3. Analyzing the Four Branches

| Producer Sends | JMS Message Type at Listener | `fromMessage` Result | Log Line |
| --- | --- | --- | --- |
| `"hello"` | `TextMessage` | `String` | `TEXT=hello` |
| `new byte[]{1,2,3}` | `BytesMessage` | `byte[]` | `BYTES=[1, 2, 3]` |
| `Map<String,Object>` | `MapMessage` | `Map` | `MAP=orderId:A42,quantity:3` |
| `Integer.valueOf(42)` | `ObjectMessage` | `Integer` | `OBJECT=42` |

If you want to actually verify **the converter is the default**, you can inject `JmsTemplate` and inspect `template.getMessageConverter()` in a Boot environment where no converter has been replaced. For example:

~~~java
System.out.println(
        jmsTemplate.getMessageConverter().getClass().getSimpleName());
~~~

In a corresponding default configuration, the output is:

~~~text
SimpleMessageConverter
~~~

**Note:** this is an illustrative debug line, not a line present in the runnable code of Section 8; if a converter bean/custom template has been registered, the class name may differ. Do not assert this class name in tests when a project intentionally configures another converter.

## 9. Receiving Messages: receiveAndConvert and @JmsListener

There are two receiving approaches to distinguish.

### 9.1. Synchronous Receive with receiveAndConvert

~~~java
// template already has a valid ConnectionFactory.
jmsTemplate.setReceiveTimeout(2_000L);

Object payload = jmsTemplate.receiveAndConvert("demo.converter");
if (payload == null) {
    System.out.println("NO_MESSAGE");
} else {
    System.out.println(payload.getClass().getName());
}
~~~

The snippet above is **not standalone** and only works when a broker/queue is available. `receiveAndConvert` uses `SimpleMessageConverter.fromMessage` if the template has not been configured with another converter. The result can be String, byte[], Map, a deserialized Serializable object, or `null` if no message arrives before the timeout.

Do not run this example concurrently with a listener consuming **the same queue** and expect both to receive the same message. A queue has competing consumers: one message is normally delivered to only **one** consumer per delivery.

### 9.2. Receiving via @JmsListener

A listener can accept a raw `jakarta.jms.Message` (as in Section 8's code), then call `SimpleMessageConverter` to clearly see the behavior. It can also accept business payload types thanks to adapters/converters configured on the listener container, though **the converter used by the listener is not necessarily the exact same bean/configuration as another custom JmsTemplate**.

If the method only accepts `String`:

~~~java
@JmsListener(destination = "demo.text")
public void consumeText(String payload) {
    System.out.println(payload);
}
~~~

that is a **snippet inside a Spring component**, requiring listener infrastructure. It suits TextMessage. However, a queue simultaneously containing BytesMessage, MapMessage, and ObjectMessage should not be consumed by a single method forcing every payload into String; you need a message type/contract convention or separate listeners.

## 10. Things SimpleMessageConverter Does NOT Do Automatically

| Wrong Expectation | Reality |
| --- | --- |
| Passing any DTO to `convertAndSend` turns it into JSON | No. The DTO must be supported by a specific branch; if Serializable it can become an ObjectMessage |
| A `String` containing JSON is auto-parsed into Map/POJO | No. It remains a TextMessage and comes back as a String when received |
| A Map with DTO/nested Map/Instant values works automatically | No. MapMessage only supports a restricted set of JMS body value types |
| `Byte[]` and `byte[]` are the same | No. Byte[] does not take the default BytesMessage branch |
| ObjectMessage needs no compatible class on the consumer | False. Java serialization/deserialization depends on classes and trust policy |
| The converter automatically creates queues/topics | No. Destinations are managed separately by JmsTemplate/provider/broker |
| The converter turns properties into POJO fields automatically | No. It primarily converts the body; header/property mapping is a separate concern |
| The converter guarantees exactly-once or retries | No. Ack, transactions, redelivery, and idempotency belong to other layers |
| Using `receiveAndConvert` alongside `@JmsListener` on one queue delivers to both | No. Queue semantics are competing consumers |
| The default JmsTemplate converter bean also applies to all custom listeners | Cannot be assumed; you must verify each container/adapter's converter |

### 10.1. What Error Occurs When Passing an Unsupported Type?

When `SimpleMessageConverter.toMessage` has no branch for a value, such as a non-Serializable `new Object()`, it throws Spring JMS `MessageConversionException` (a runtime exception). When MapMessage rejects a value, or ObjectMessage is blocked by the provider, the error may originate from a provider `JMSException`/conversion error and be wrapped by Spring along the call path.

Anti-example:

~~~java
// Java Object does not implement Serializable and is not String/byte[]/Map.
jmsTemplate.convertAndSend("demo.converter", new Object());
~~~

This snippet can **compile**, but is rejected when the converter attempts to convert the payload. Do not work around this by calling `toString()` on every object in the system: `Object.toString()` strings are usually not a stable format for service communication.

### 10.2. When Do You Need Another Converter?

If the system uses **DTOs/records**, wants **JSON** instead of Java serialization, and requires cross-language communication, use an appropriate JSON converter, such as `MappingJackson2MessageConverter` in Spring Framework 6.x with the corresponding Jackson 2 dependency.

An illustrative configuration:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JsonJmsConverterConfig {

    @Bean
    MessageConverter jsonMessageConverter() {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        return converter;
    }
}
~~~

**This is only an example converter configuration, not a full application.** You need the Jackson dependency, explicit type-id/trust mappings, and to verify whether this bean is actually wired into JmsTemplate/listener containers in the Boot version being used. Do not blindly allow deserializing any class specified by a message. With Spring 7+, some converter APIs are updated; follow the actual version's Javadoc when upgrading.

If you need JSON formatting while still keeping SimpleMessageConverter, you can serialize to a String on the producer and parse on the consumer. However, your code must manage formatting, errors, and schemas manually; do not describe that as SimpleMessageConverter converting Java DTOs to JSON automatically.

## 11. Differences Between MapMessage and ObjectMessage

A practical question: both Java `Map` and `ArrayList` typically implement `Serializable`, so which JMS message type will SimpleMessageConverter create?

~~~java
Map<String, Object> map = Map.of("orderId", "A42");
jmsTemplate.convertAndSend("demo.converter", map);
// MapMessage, because the Map branch is checked separately.

java.util.List<String> list = java.util.List.of("A42", "B7");
jmsTemplate.convertAndSend("demo.converter", list);
// Can be ObjectMessage because the List implementation is Serializable.
~~~

This is a snippet inside a method; `List.of(...)` returns an object of an internal JDK implementation, where Serializable is not a general API contract across all List implementations. For examples needing clear guarantees, use `new java.util.ArrayList<>(...)` (Serializable). Key takeaway: **only Map takes the MapMessage branch**; there is no automatic List → MapMessage conversion.

Comparing MapMessage vs ObjectMessage:

| Aspect | MapMessage | ObjectMessage |
| --- | --- | --- |
| Body format | JMS key/value fields | One Serializable object |
| Type conversion | Based on the valid MapMessage type set | Java serialization |
| Portability | Can interoperate with other JMS clients if adhering to JMS types | Tied to Java/classes/serialization; hard to interoperate across languages |
| Selector | Does not read fields in the body; still reads message properties | Does not read object fields in the body |
| Risks | Unsupported value types, schema drift | Class versions, deserialization security, trust-list |
| Alternative | JSON/Avro/Protobuf with a custom converter when needed | JSON/explicit schema format for cross-service |

Therefore, `SimpleMessageConverter` cannot be called a "JSON serializer" or a "JavaBean mapper". It is simply a default mapping of **four common JMS message groups**.

## 12. Message Contract Design Rules

Align producer and consumer on **Java payload**, **JMS message type**, **body schema**, and **metadata**. An illustrative contract:

~~~yaml
destination: demo.converter
jmsMessageType: MapMessage
bodyFields:
  orderId: {type: String, example: A42}
  quantity: {type: int, example: 3}
properties:
  eventType: {type: String, example: ORDER_CREATED}
  schemaVersion: {type: int, example: 1}
~~~

This is a **contract specification document**, not Spring Boot `application.yml` content. Without a documented contract, a consumer seeing only a `MapMessage` might not know whether the `quantity` field is sent as an `int` or a `String`, or whether `eventType` lives in the body or in properties.

Some principles:

1. If using a `TextMessage` containing JSON, specify encoding, schema version, validation, and size limits.
2. If using a `BytesMessage`, specify MIME/schema/codec (if needed) and avoid decoding bytes with an unagreed charset.
3. If using a `MapMessage`, use String keys, values within the JMS-accepted set, and no arbitrary nested DTOs.
4. If using an `ObjectMessage`, control the classpath and allowlist, avoid untrusted sources, and consider JSON as an alternative.
5. Keep `JMSCorrelationID`, `JMSReplyTo`, `JMSDestination`, and message properties in their proper layer; do not stuff them into the body just for "convenient conversion".
6. Do not use a converter to mask routing, transaction, or message selection errors.

## 13. Common Errors and Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `MessageConversionException` on `convertAndSend(new Object())` | Object is not String, byte[], Map, or Serializable | Use a supported type or a custom converter |
| Sent DTO but receiver cannot read it | Serializable DTO became ObjectMessage, class/serialVersionUID mismatch | Align classes/compatibility or switch to JSON |
| Artemis/Java reports deserialization rejected | ObjectMessage contains a class outside the allowlist or blocked | Check provider policy; trust only required classes |
| Error sending Map with `List`/`Instant` value | MapMessage does not support arbitrary Java objects | Encode body as JSON or fix schema value types |
| Consumer expects String but receives MapMessage | Producer sent Map, not JSON String | Align message contract and converter |
| Consumer receives byte[] and decodes garbled text | Wrong charset/codec | Standardize UTF-8 or explicit binary format |
| `Byte[]` arrives as a different type than `byte[]` | Wrapper array took the Serializable branch | Use primitive `byte[]` |
| `receiveAndConvert` returns null | Timeout/empty queue/no matching message yet | Check receive timeout, queue metrics, and competing consumers |
| Flaky test because listener and synchronous receive share a queue | Two competing consumers | Use separate queues in tests or stop the listener when testing receive |
| Error when using non-String Map key | MapMessage requires String key names | Standardize String keys |
| Properties do not appear in `fromMessage` body | Converter only extracts the body | Read headers/properties on the raw JMS Message |
| JSON text does not become a POJO | SimpleMessageConverter does not parse JSON | Attach a JSON converter or parse explicitly |
| `@JmsListener` receives nothing | Wrong queue/topic, ACL, selector, or container | Check broker, destination, permissions, and listener configuration |

### 13.1. Troubleshooting Along the Causal Chain

When conversion fails, check in order:

~~~text
Java type at producer
      ↓
Which JMS Message type does toMessage() choose?
      ↓
Are Map values / Serializable valid?
      ↓
Does the provider accept the payload and send permissions?
      ↓
Which JMS Message type does the consumer actually receive?
      ↓
Can fromMessage() read the body and deserialize?
      ↓
How does the application validate the result type and schema?
~~~

Log the producer Java type, JMS type at receiver, destination, correlation/business ID, and error class. Avoid logging sensitive data or entire raw ObjectMessages. The presence of a message on the broker does not mean the receiving converter has the classes or permissions to read it.

## 14. Self-Check Questions

**Question 1.** Why does `jmsTemplate.convertAndSend("queue", "hello")` create a TextMessage instead of an ObjectMessage even though String implements Serializable?

**Answer:** SimpleMessageConverter prioritizes the String → TextMessage branch before the Serializable → ObjectMessage branch.

**Question 2.** Does a `Map<String, Object>` containing `quantity=3` let the selector `quantity > 2` filter automatically?

**Answer:** No. MapMessage stores `quantity` in the **body**. Selectors only see JMS properties and supported headers; the producer must set a separate property if broker filtering is needed.

**Question 3.** Do sending `byte[] {1,2,3}` and `Byte[] {1,2,3}` produce the same JMS type?

**Answer:** No. `byte[]` uses the BytesMessage branch; `Byte[]` does not match the primitive byte array branch and can become an ObjectMessage via Serializable.

**Question 4.** A Java record does not implement Serializable and is not String/byte[]/Map. Does SimpleMessageConverter automatically turn it into JSON?

**Answer:** No. It has no automatic JSON rule; a separate converter is needed or the payload must be serialized to a string first.

**Question 5.** Does `JmsTemplate.send(session -> session.createTextMessage(...))` call `SimpleMessageConverter.toMessage`?

**Answer:** No. You manually created the JMS Message; `send` simply sends it through the template pipeline.

**Question 6.** Why does ObjectMessage require more security attention than a TextMessage containing JSON?

**Answer:** ObjectMessage uses Java deserialization, exposing risks when deserializing untrusted classes and depending on trust lists/classpath; JSON also needs validation and safe type mapping, but does not require Java object deserialization by default.

**Question 7.** Does `receiveAndConvert` return a Map or a JSON String when a consumer receives a MapMessage?

**Answer:** A Java Map according to SimpleMessageConverter rules, not a JSON String.

**Question 8.** When `receiveAndConvert("queue")` returns null after timeout, can we conclude the converter is broken?

**Answer:** No. Simply no message may have been received within the wait window. Check the broker queue, competing listeners, and timeout.

**Question 9.** Can an `Integer` be received via ObjectMessage?

**Answer:** Yes: `Integer` implements Serializable and is not a String, byte[], or Map, provided the provider permits its serialization/deserialization.

**Question 10.** When should `MappingJackson2MessageConverter` be used instead of SimpleMessageConverter?

**Answer:** When schema-backed JSON is needed, mapping DTOs/records and avoiding Java ObjectMessage coupling in inter-service communication, with appropriate Jackson, type-id, and trust controls.

## Official References

- [Spring Framework — Sending a Message, Using JMS Message Converters](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html): describes default SimpleMessageConverter, `convertAndSend`, `receiveAndConvert`, and `MessagePostProcessor`.
- [Spring Framework API — SimpleMessageConverter (6.1.8)](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): covers TextMessage, BytesMessage, MapMessage, ObjectMessage, and Java type rules.
- [Spring Framework API — MessageConverter (6.2.14)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html): `toMessage(Object, Session)` and `fromMessage(Message)`.
- [Spring Framework API — MappingJackson2MessageConverter (6.2.19)](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): JSON converter and message type configuration.
- [Spring Boot 3.4 — JMS, ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html): starter, `native` mode, and `ConnectionFactory`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS message types, MapMessage, ObjectMessage, selectors, and message properties.
