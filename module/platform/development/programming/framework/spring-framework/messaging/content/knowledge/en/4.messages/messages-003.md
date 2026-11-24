# GenericMessage and Creating Standard Messages in Spring Framework

## 1. Where Does GenericMessage Fit in the Messaging Model?

Spring Messaging standardizes exchanged data into a message. Instead of passing only a payload object, the application can wrap the payload together with metadata so components handle them consistently.

The core model consists of three parts:

- **Message<T>:** an interface representing a message with a payload of type T and a set of headers.
- **GenericMessage<T>:** the common implementation of Message<T>, used for regular payloads.
- **MessageHeaders:** a key-value collection of metadata attached to the message.

A message can be visualized as follows:

~~~text
Message<OrderCreated>
├── payload
│   └── OrderCreated(orderId = "ORD-1001")
└── headers
    ├── id
    ├── timestamp
    ├── correlationId = "corr-1001"
    └── source = "checkout"
~~~

The payload describes the **main data to be processed**. Headers describe the **accompanying context** such as identifier, creation time, correlation ID, content type, reply channel, or auxiliary business metadata.

The Message<T> interface has only two important methods:

- getPayload(): returns the payload of type T.
- getHeaders(): returns MessageHeaders; the result is non-null, though it may contain no custom headers.

GenericMessage<T> resides in the org.springframework.messaging.support package. It is a concrete implementation for creating messages without writing a custom class implementing Message.

Three concepts should be distinguished:

- **Payload:** the business object, e.g., OrderCreated, String, byte[], or a DTO.
- **Message:** a standardized wrapper for the payload and headers.
- **Channel/transport:** the mechanism for receiving, sending, or transporting a Message. GenericMessage itself is not a queue, broker, socket, or data-sending mechanism.

## 2. What Is GenericMessage<T>?

GenericMessage<T> implements Message<T> and Serializable. Once created, the message is immutable: there is no API to replace the payload or mutate the header structure of that message itself.

The class provides three commonly used constructors:

~~~java
new GenericMessage<>(payload);
new GenericMessage<>(payload, headersMap);
new GenericMessage<>(payload, messageHeaders);
~~~

Where:

1. **GenericMessage(T payload):** creates a message with the payload and a default set of headers.
2. **GenericMessage(T payload, Map<String, Object> headers):** creates a message with the supplied headers. The contents of the Map are copied upon initialization.
3. **GenericMessage(T payload, MessageHeaders headers):** uses the supplied MessageHeaders instance directly without copying it.

The payload must not be null. If business logic needs to represent a "no data" state, design an explicit payload such as a dedicated record/event or an appropriate wrapper type, rather than passing null into GenericMessage.

### 2.1. Creating a message with only a payload

The shortest way is to pass an object to the constructor:

~~~java
OrderCreated event = new OrderCreated("ORD-1001");

Message<OrderCreated> message = new GenericMessage<>(event);
~~~

Spring creates MessageHeaders automatically. By default, headers contain a framework-managed ID and timestamp. The application can read the payload and headers through the Message interface:

~~~java
OrderCreated body = message.getPayload();

String messageId = message.getHeaders().getId().toString();
Long createdAt = message.getHeaders().getTimestamp();
~~~

The message ID helps identify a message instance. If you need to link multiple messages within the same business flow, use a custom header such as correlationId or a business key. When creating a new message from an old message, the ID may be regenerated; do not use the default ID as an end-to-end transaction ID if the business logic requires a stable identifier.

### 2.2. Creating a message with a Map of headers

When you need to add metadata, pass a Map<String, Object> to the constructor:

~~~java
Map<String, Object> headers = new HashMap<>();
headers.put("correlationId", "corr-1001");
headers.put("source", "checkout");
headers.put("attempt", 1);

Message<OrderCreated> message =
    new GenericMessage<>(event, headers);
~~~

Header names are String, while values can be Object. Producer and consumer should agree on header names, data types, and their meanings.

You can read header values with the expected type:

~~~java
String correlationId =
    message.getHeaders().get("correlationId", String.class);

Integer attempt =
    message.getHeaders().get("attempt", Integer.class);
~~~

MessageHeaders supports typed access via get(key, Class<T>). If you use plain get(Object), the result has type Object and the application must check/cast the type itself.

**Note on Map copying:** GenericMessage(payload, Map) copies the key-value pairs into the headers when creating the message. Therefore, modifying the original Map afterward does not alter the message's header structure:

~~~java
Map<String, Object> headers = new HashMap<>();
headers.put("source", "checkout");

Message<String> message = new GenericMessage<>("created", headers);

headers.put("source", "admin");

System.out.println(message.getHeaders().get("source"));
~~~

The result is still checkout. This is a shallow copy of the Map structure, not a deep copy of every object stored as a value. If a header contains a mutable object, that object can still be modified through another reference. Prefer simple, immutable, and easily serializable header values.

### 2.3. Creating a message with existing MessageHeaders

The constructor taking MessageHeaders uses the supplied instance directly:

~~~java
MessageHeaders messageHeaders = new MessageHeaders(headers);

Message<String> message =
    new GenericMessage<>("created", messageHeaders);
~~~

This approach is suitable when you already have MessageHeaders created from another processing flow. Since MessageHeaders is immutable, sharing the instance does not allow consumers to directly modify the header structure.

In typical applications, the constructor accepting a Map or MessageBuilder is usually easier to read. Only use the MessageHeaders overload when you genuinely need to reuse a pre-built set of headers and clearly understand that the instance is not copied.

## 3. MessageHeaders and Important Headers

MessageHeaders implements Map<String, Object>, but it is a read-only Map. Mutating operations such as put, putAll, remove, or clear will throw UnsupportedOperationException.

Do not write the following:

~~~java
message.getHeaders().put("correlationId", "corr-2001");
~~~

To change metadata, create a new message with new headers using MessageBuilder or an appropriate MessageHeaderAccessor.

Some standard Spring headers:

| Header | Meaning |
|---|---|
| id | Spring-managed message instance identifier |
| timestamp | Message creation time according to the default mechanism |
| contentType | Describes the content type, typically related to payload conversion |
| replyChannel | Channel used for the reply path in some request-reply models |
| errorChannel | Channel used for error handling in some messaging models |

You can use constants on MessageHeaders to avoid typos in header names, such as MessageHeaders.ID, MessageHeaders.TIMESTAMP, and MessageHeaders.CONTENT_TYPE.

In addition to standard headers, the application can add custom headers:

- correlationId: links the message to a request or business flow.
- tenantId: identifies the tenant in a multi-tenant system.
- source: the component emitting the message.
- eventType or schemaVersion: describes the data type/version number when a clear convention exists.
- traceId: links logs and distributed traces if the system has standardized trace context propagation.

Do not put all business data into headers. The payload is where the main content belongs; headers should only contain metadata for routing, tracking, conversion, or cross-pipeline processing.

ID and timestamp are headers managed by Spring. MessageBuilder does not allow overwriting them through ordinary header copy operations. Do not use them to store order IDs or business correlation IDs.

## 4. Creating Messages with MessageBuilder

In application code, MessageBuilder is usually the flexible and readable way to create messages. The builder lets you set the payload and headers step by step, and then build() returns a Message.

Example:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1002"))
    .setHeader("correlationId", "corr-1002")
    .setHeader("source", "order-service")
    .setHeaderIfAbsent("attempt", 1)
    .build();
~~~

MessageBuilder creates a regular GenericMessage; if the payload is a Throwable, the builder creates an ErrorMessage appropriate for the error content.

Commonly used methods:

| Method | Purpose |
|---|---|
| withPayload(payload) | Starts the builder with a payload |
| setHeader(name, value) | Adds or replaces a header; a null value removes that header |
| setHeaderIfAbsent(name, value) | Sets the header only if it is not already present |
| copyHeaders(map) | Copies headers from a Map; existing custom values may be overwritten |
| copyHeadersIfAbsent(map) | Adds only headers that do not yet exist |
| removeHeader(name) | Removes a header |
| removeHeaders(patterns...) | Removes headers matching name patterns |
| build() | Creates a new Message from the configured payload and headers |

### 4.1. setHeader and setHeaderIfAbsent

Use setHeader when a value needs to be set explicitly:

~~~java
Message<String> message = MessageBuilder
    .withPayload("payment-completed")
    .setHeader("source", "payment-service")
    .setHeader("attempt", 2)
    .build();
~~~

Use setHeaderIfAbsent when you want to preserve an existing value:

~~~java
Message<String> message = MessageBuilder
    .withPayload("payment-completed")
    .setHeaderIfAbsent("source", "default-service")
    .build();
~~~

If source already exists in the builder, setHeaderIfAbsent does not overwrite it. If the value passed to setHeader is null, the builder removes the corresponding header.

### 4.2. copyHeaders and copyHeadersIfAbsent

When metadata is already in a Map, you can copy multiple headers at once:

~~~java
Map<String, Object> metadata = Map.of(
    "correlationId", "corr-3001",
    "source", "checkout",
    "tenantId", "tenant-a"
);

Message<String> message = MessageBuilder
    .withPayload("order-created")
    .copyHeaders(metadata)
    .build();
~~~

copyHeaders can overwrite previously set custom header values. copyHeadersIfAbsent only fills in headers that do not yet exist. ID and timestamp are read-only headers per Spring's rules and are not overwritten by ordinary copy operations.

### 4.3. Creating a new message from an existing message

MessageBuilder.fromMessage(existingMessage) creates a new builder with the payload and headers taken from the original message. This is a suitable way to add metadata in a pipeline:

~~~java
Message<OrderCreated> enriched = MessageBuilder
    .fromMessage(originalMessage)
    .setHeader("processedBy", "inventory-service")
    .setHeader("attempt", 2)
    .build();
~~~

A new message is created; the original message is not modified. The payload is reused from the old message, so if the payload is a mutable object, both messages may still reference that same object. ID/timestamp are framework-managed metadata; do not assume the new message keeps the same ID as the old message.

### 4.4. createMessage

MessageBuilder also has a factory method:

~~~java
Message<OrderCreated> message =
    MessageBuilder.createMessage(payload, messageHeaders);
~~~

This factory creates a Message with the provided payload and MessageHeaders. The MessageHeaders instance is used directly without copying. Ensure both payload and messageHeaders are non-null.

## 5. Standalone Java 17+ Example

The example below compares the GenericMessage constructor, the builder, and creating a new message from an existing message. The program also shows that modifying the original Map does not alter the copied headers structure.

**Project structure**

~~~text
generic-message-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          GenericMessageDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>generic-message-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.0</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/GenericMessageDemo.java**

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.messaging.support.MessageBuilder;

public class GenericMessageDemo {

    public record OrderCreated(String orderId) {}

    public static void main(String[] args) {
        OrderCreated payload = new OrderCreated("ORD-1001");

        // 1. Create a message directly using GenericMessage and a Map of headers.
        Map<String, Object> initialHeaders = new HashMap<>();
        initialHeaders.put("correlationId", "corr-1001");
        initialHeaders.put("source", "checkout");

        Message<OrderCreated> directMessage =
            new GenericMessage<>(payload, initialHeaders);

        // The original Map changes, while the message headers keep the copied value.
        initialHeaders.put("source", "changed-outside");

        System.out.println("directPayload=" + directMessage.getPayload());
        System.out.println(
            "directSource=" + directMessage.getHeaders().get("source")
        );
        System.out.println(
            "directCorrelationId=" +
            directMessage.getHeaders().get("correlationId")
        );

        // 2. Create a message using MessageBuilder.
        Message<OrderCreated> builtMessage = MessageBuilder
            .withPayload(payload)
            .setHeader("correlationId", "corr-1002")
            .setHeaderIfAbsent("source", "order-service")
            .build();

        // 3. Create a new message from an existing message.
        Message<OrderCreated> enrichedMessage = MessageBuilder
            .fromMessage(builtMessage)
            .setHeader("attempt", 2)
            .build();

        System.out.println(
            "builtCorrelationId=" +
            builtMessage.getHeaders().get("correlationId")
        );
        System.out.println(
            "builtSource=" + builtMessage.getHeaders().get("source")
        );
        System.out.println(
            "enrichedAttempt=" + enrichedMessage.getHeaders().get("attempt")
        );
        System.out.println(
            "enrichedSource=" + enrichedMessage.getHeaders().get("source")
        );
        System.out.println(
            "payloadSameReference=" +
            (directMessage.getPayload() == enrichedMessage.getPayload())
        );
    }
}
~~~

Run from the generic-message-demo directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GenericMessageDemo
~~~

**stdout**

~~~text
directPayload=OrderCreated[orderId=ORD-1001]
directSource=checkout
directCorrelationId=corr-1001
builtCorrelationId=corr-1002
builtSource=order-service
enrichedAttempt=2
enrichedSource=order-service
payloadSameReference=true
~~~

The output shows:

- GenericMessage stores the payload and a structural copy of the headers Map at creation time.
- MessageBuilder creates a new message from the payload and configured metadata.
- fromMessage lets you add headers without modifying the original message.
- The new message's payload can still be the same object as the old message's payload; an immutable message does not mean the payload is always immutable.

## 6. Sending GenericMessage into a Processing Flow

GenericMessage is typically sent through a MessageChannel or created by the framework when a component converts data into a Message. Example of sending to a channel:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1003"))
    .setHeader("correlationId", "corr-1003")
    .build();

boolean accepted = channel.send(message);
~~~

MessageChannel is the abstraction for sending messages. Whether the message is processed synchronously, asynchronously, in memory, or through an adapter depends on the channel implementation and system configuration. Creating a GenericMessage does not automatically send the message anywhere.

When payload conversion is needed, Spring Messaging has the MessageConverter system. A converter is responsible for converting between the payload and a data type suitable for a protocol or endpoint. GenericMessage remains an in-application message object; to cross the network, the integration layer must know how to serialize/convert the payload and map headers to the transport's format.

If an API or listener accepts Message<T>, you can pass GenericMessage<T> directly because GenericMessage implements Message<T>. If it only accepts the payload, the framework can resolve the payload from the message depending on the handler/argument resolver being used.

## 7. When to Use GenericMessage vs. MessageBuilder?

| Situation | Appropriate approach |
|---|---|
| Only need to wrap a payload into a message | new GenericMessage<>(payload) |
| Already have a header Map and want quick creation | new GenericMessage<>(payload, headers) |
| Need to set multiple headers step by step | MessageBuilder.withPayload(...) |
| Need a default header if not yet present | setHeaderIfAbsent(...) |
| Need to merge metadata from a Map | copyHeaders(...) or copyHeadersIfAbsent(...) |
| Need to add headers to an existing message | MessageBuilder.fromMessage(...) |
| Already have MessageHeaders and want to reuse the instance | GenericMessage or MessageBuilder.createMessage(...) |
| Need advanced header manipulation or protocol-based header management | See MessageHeaderAccessor and subclasses |

In ordinary business code, prefer MessageBuilder when multiple headers are needed or when creating a message from an existing one. The GenericMessage constructor is appropriate when the structure is simple, clear, and you already have the payload/Map. Both approaches produce a structurally immutable Message.

## 8. Common Mistakes and Caveats

1. **Confusing GenericMessage with a queue or broker:** GenericMessage is just an object representing a message. It does not store a queue, send itself over the network, or create consumers.
2. **Trying to modify MessageHeaders after building:** MessageHeaders is read-only. To change metadata, build a new message.
3. **Assuming an immutable message makes the payload immutable:** GenericMessage does not change the payload reference, yet the object inside the payload may still be mutable.
4. **Assuming a headers Map is deeply copied:** the constructor taking a Map copies the key-value structure, not deep-cloning every value.
5. **Passing a null payload:** GenericMessage requires a non-null payload. Model the absence of data with a meaningful payload type.
6. **Using headers instead of the payload:** primary business data belongs in the payload; headers are for metadata.
7. **Using the default ID as a correlation ID:** the ID identifies the message instance. Create a separate correlationId or business key for the business flow.
8. **Inconsistent header types:** producer and consumer must agree on data types. For example, attempt should always be Integer, and correlationId should always be String.
9. **Assuming Serializable means any payload can be transmitted:** GenericMessage implements Serializable, yet the payload and header values must also be compatible with the serialization mechanism in use. JSON converters also have their own rules.
10. **Using arbitrary headers without control:** only transmit necessary metadata; avoid putting secrets, tokens, or sensitive data into message headers because they can appear in logs or be forwarded through adapters.

## 9. Conclusion

GenericMessage<T> is the common implementation of Message<T> in Spring Messaging. It wraps a non-null payload along with MessageHeaders and provides an immutable message after creation. You can create a message using its constructor directly, passing a Map of headers, or using MessageBuilder to set, copy, and remove headers clearly.

Choose the constructor when the message is simple; choose MessageBuilder when multiple metadata operations are needed or when creating a new message from an existing message. Always keep the payload for primary data, headers for metadata, and remember that GenericMessage does not itself provide a channel, queue, broker, or transport mechanism.

## 10. References

- [Message<T> — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/Message.html)
- [GenericMessage<T> — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/GenericMessage.html)
- [MessageBuilder<T> — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [MessageHeaders — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/MessageHeaders.html)