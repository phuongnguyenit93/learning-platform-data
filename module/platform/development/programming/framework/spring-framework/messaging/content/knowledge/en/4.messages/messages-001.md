# Message<T> Structure: Payload and Headers in Spring Messaging

## 1. What is a Message?

In Spring Messaging, **Message<T>** is a standardized data envelope for components in an application to exchange information. Each message consists of two parts:

1. **Payload:** the main content that the receiver needs to process.
2. **Headers:** a set of metadata describing the context, routing, or how to process the payload.

This can be modeled as:

~~~text
Message<T>
+--------------------------------------+
| payload: T                           |
|                                      |
| headers: MessageHeaders              |
|   id                                 |
|   timestamp                          |
|   contentType                        |
|   correlationId (if needed by app)   |
|   tenantId (if needed by app)        |
+--------------------------------------+
~~~

For example, when publishing an order event, the payload might contain the order ID and total amount. The headers might contain the tenant ID, correlation ID, or content type. As a result, the handler receives both the business data and the information needed to track and route the message.

Message<T> is an abstraction of Spring Messaging, located in the org.springframework.messaging package. It is not a network protocol or a message broker. A message can be passed between components within the same process, through a channel, or mapped by an adapter to an external protocol.

## 2. Payload: The Main Data Part

### 2.1 What content does the payload carry?

The payload is the object that the message intends to deliver to the receiver. Its data type can be:

- String for text or simple content.
- byte[] for binary data.
- A DTO or Java record for commands, events, and business data.
- An Object supported by a serializer or message converter.
- Another data type that the receiving component can understand and process.

For example, the payload of an OrderCreated event could be:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        long totalAmount
) {
}
~~~

This payload describes a business event. The orderId, customerId, and totalAmount fields belong to the content that the consumer needs to understand to perform its work.

### 2.2 Choosing a clear payload type

Use specific types to express the data contract:

- Message<OrderCreated> for a message containing an order created event.
- Message<CreateOrderCommand> for a message containing an order creation request.
- Message<String> for a text message.
- Message<byte[]> for binary data.

When a component needs to handle multiple payload types, Message<?> can be used. The ? means the payload type is not specifically determined at the declaration site; the handler needs to check or convert it appropriately before use.

Do not overuse Message<Object> just to group all message types together. Message<OrderCreated> and Message<Object> are two different generic types; Java generics are not covariant in that way. Message<?> is usually a more appropriate choice when needing to receive messages with multiple payload types.

### 2.3 Payload and data conversion

The payload in memory can be a Java object. When crossing a protocol or broker boundary, the object usually needs to be converted into a data format that the receiver can decode, such as JSON or a byte array.

Spring Messaging provides the MessageConverter abstraction for payload conversion. Three things should be distinguished:

- Creating a message in the application.
- Converting the payload from an object to a transport format.
- Converting the received data back into the payload type expected by the consumer.

Having Message<T> does not mean an object payload is automatically serialized or that every adapter uses the same converter. You need to configure the converter and agree on the schema between the sender and the receiver.

## 3. Headers: Metadata Accompanying the Payload

### 3.1 Role of headers

Headers describe the message and its processing context. They should not become the place to store all business data.

Some common metadata groups:

| Group | Examples | Purpose |
|---|---|---|
| Identification | id, timestamp | Identify the message and its creation time |
| Format | contentType | Hint at how to interpret or convert the payload |
| Correlation | correlationId, traceId | Link multiple steps within the same processing flow |
| Routing | destination or route information | Indicate the target receiver according to the integration mechanism |
| Application context | tenantId, locale | Supply necessary context for processing |
| Delivery control | delivery attempt or adapter-specific ACK info | Support infrastructure delivery policies |

The names in the table are examples of metadata. Not all of them are default headers of Spring Messaging. MessageHeaders defines standard names such as id, timestamp, and contentType; headers like tenantId, correlationId, or traceId are typically defined by the application, integration library, or adapter.

Some specific headers such as replyChannel and errorChannel may appear in Spring Integration flows. You should not assume they exist in every Spring Messaging message.

### 3.2 Distinguishing payload and header

| Criterion | Payload | Header |
|---|---|---|
| Answers the question | What content does the message carry? | What context or metadata does the message have? |
| Examples | OrderCreated, CreateOrderCommand | correlationId, tenantId, contentType |
| Structure | Follows the business schema | Follows metadata conventions |
| Usage | Consumer reads and processes the main data | Infrastructure or handler uses it for routing, tracking, and control |
| Size | Can contain large business data | Should be small, concise, and have a clear meaning |

A useful rule: if the consumer needs a data field to make a business decision, that field usually belongs in the payload. If the field only describes how to track, format, or forward the message, it usually fits in a header.

For example, the order's totalAmount should be in the payload because it is business data. correlationId fits in a header because it links the message to a processing flow. If tenantId determines data ownership, it must be verified from a trusted security context; a header sent by a client must not be treated as proof of tenant authentication.

### 3.3 Headers are not a place to store secrets

Do not put passwords, access tokens, private keys, or sensitive data into headers without clear requirements and protective measures. Headers may be logged, displayed in tracing, passed through a broker, or mapped by an adapter to another protocol.

You should also avoid putting large payloads into headers. Business data should reside in the payload or a dedicated store; headers should only hold the metadata needed for reference.

## 4. Core APIs

### 4.1 Message<T>

Message<T> is the interface representing a message. Two important methods:

- getPayload() returns the payload of type T.
- getHeaders() returns the MessageHeaders collection.

A consumer can accept Message<?> if it does not need to know the payload type at declaration time, or use Message<OrderCreated> when the input contract is clear.

### 4.2 MessageHeaders

MessageHeaders is the type that holds the headers of a message. It implements Map<String, Object> for access by header name, and also provides constants for several standard headers:

- MessageHeaders.ID
- MessageHeaders.TIMESTAMP
- MessageHeaders.CONTENT_TYPE

Access example:

~~~java
Object tenantId = message.getHeaders().get("tenantId");
Object correlationId = message.getHeaders().get("correlationId");
~~~

You can use typed retrieval APIs in appropriate cases; if retrieving via Map.get, you need to check and cast the type safely.

MessageHeaders provides a read-only view of the header collection. After a message is created, you should not modify the header map directly. Use a builder or accessor to create a new message with updated metadata.

Note: a header map that does not allow direct modification does not mean the entire message is deeply copied. Values stored in headers can be objects with mutable state; the payload can also be a mutable object. If multiple components hold references to that object, changes to its contents can be observed elsewhere. Prefer immutable payloads and header values, such as records, String, UUID, or appropriate value object types.

### 4.3 GenericMessage<T>

GenericMessage<T> is the basic implementation of Message<T>. In most cases when creating messages at the application layer, you can use MessageBuilder so you do not have to manage MessageHeaders creation manually.

### 4.4 MessageBuilder<T>

MessageBuilder is a convenient API for constructing messages. Two common ways to initialize it:

- MessageBuilder.withPayload(payload) creates a message from a new payload.
- MessageBuilder.fromMessage(existingMessage) creates a builder based on an existing message.

Common operations:

- setHeader(name, value) sets or replaces a header value.
- setHeaderIfAbsent(name, value) sets the header only if it does not already exist.
- removeHeader(name) removes a header.
- copyHeaders(map) copies headers from a map.
- copyHeadersIfAbsent(map) copies only headers that do not yet exist.
- build() creates the complete message.

Using a builder helps create a new message with a consistent structure. Do not modify MessageHeaders directly after a message has been sent.

## 5. Creating and Reading Message<T> in Java

The following example is a complete Java 17 class using the org.springframework:spring-messaging dependency. In a Maven or Gradle project, declare this dependency and manage versions consistently using the Spring Framework BOM or Spring Boot dependency management.

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageStructureDemo {

    record OrderCreated(String orderId, BigDecimal total) {
    }

    public static void main(String[] args) {
        OrderCreated payload = new OrderCreated(
                "ORD-1001",
                new BigDecimal("125000")
        );

        Message<OrderCreated> message = MessageBuilder
                .withPayload(payload)
                .setHeader("tenantId", "acme")
                .setHeader("correlationId", "corr-001")
                .build();

        System.out.println(message.getPayload().orderId());
        System.out.println(message.getPayload().total());
        System.out.println(message.getHeaders().get("tenantId"));
        System.out.println(message.getHeaders().get("correlationId"));
    }
}
~~~

Output when run:

~~~text
ORD-1001
125000
acme
corr-001
~~~

In the example:

- OrderCreated is a specific payload type.
- Message<OrderCreated> represents a message whose payload type is OrderCreated.
- tenantId and correlationId are application-defined metadata.
- getPayload() returns the business object.
- getHeaders() provides the accompanying metadata.

The program requires spring-messaging and its corresponding transitive dependencies on the classpath. You can run the main class using an IDE or the project's Java run task after Maven/Gradle has resolved the dependencies.

## 6. Creating a New Message from an Existing Message

In a pipeline, a handler sometimes needs to add metadata or replace the payload. Create a new message from the original message using fromMessage:

~~~java
Message<OrderCreated> enriched = MessageBuilder
        .fromMessage(message)
        .setHeader("source", "order-service")
        .setHeaderIfAbsent("schemaVersion", 1)
        .build();
~~~

The builder copies the existing message's information to create a new message. The payload remains the old object if you do not replace the payload; the operation above does not automatically create a deep copy of the payload object.

If you need to replace the payload, use the builder with the new payload or the payload-replacement method supported by the builder in the version you are using. When changing the payload type, declare the corresponding generic type and ensure downstream consumers understand the new schema.

Do not copy all headers from an untrusted source and forward them as-is. For messages crossing system boundaries, selectively allow which headers to keep, normalize names and data types, remove internal metadata that is no longer meaningful, and verify fields that affect access control.

## 7. MessageHeaderAccessor and Specialized Headers

When you need controlled header manipulation or need to work with protocol-specific metadata, Spring provides MessageHeaderAccessor. Specialized accessors extend this approach, such as accessors for STOMP or Simp messaging.

An accessor is useful when:

- You need to read or set a group of related headers.
- You need to work with native protocol headers.
- You need to distinguish application headers from framework-managed headers.
- You need to create a message after finishing metadata updates.

While building a message, an accessor can provide a mutable header manipulation phase. Once the message is finalized and published, the headers transition to a read-only state according to the framework's mechanism. Follow the accessor's lifecycle and avoid retaining a mutable accessor to modify a message after it has been sent.

For ordinary needs such as adding tenantId or correlationId, MessageBuilder is usually easier to read and sufficient. Use a specialized accessor when you need specific capabilities that the general-purpose builder does not express clearly.

## 8. Message Lifecycle in a Processing Flow

A messaging flow typically has the following steps:

~~~text
Business payload
       |
       v
MessageBuilder.withPayload(...)
       |
       v
Message<T>
  + payload
  + headers
       |
       v
MessageChannel.send(message)
       |
       v
MessageHandler.handleMessage(message)
       |
       +---- read payload
       |
       +---- read metadata
       |
       +---- process or create new message
~~~

The abstractions have different responsibilities:

- Message<T> describes the data and metadata.
- MessageChannel is the point where messages are sent.
- MessageHandler is the component that receives and processes messages.
- An adapter or broker can transfer messages across system boundaries.

A channel accepting a message does not mean business processing has succeeded. If you need completion confirmation, retries, or delivery guarantees, use the appropriate mechanism of the channel, adapter, or broker being used.

## 9. Considerations When Designing Payloads and Headers

### 9.1 Keep payloads stable and versioned

The payload is the data contract between producer and consumer. When the schema changes, you need to consider backward and forward compatibility:

- Add new fields with appropriate default rules.
- Avoid renaming or changing the type of fields currently used by consumers without a migration plan.
- Define how to handle missing fields, extra fields, and invalid values.
- Consider a schema version field in the payload or metadata if the system needs to manage multiple versions.

Do not assume the serializer can resolve all schema changes on its own. Producer and consumer must agree on how to interpret the data.

### 9.2 Use headers for stable metadata

Headers should be small, meaningful, and follow consistent conventions. For example:

- correlationId to connect messages within the same request.
- traceId to link with distributed tracing if the system uses tracing.
- tenantId to provide tenant context after verifying a trusted source.
- contentType to describe the content format when a converter or adapter needs it.

Avoid creating multiple nearly synonymous header names like requestId, reqId, correlation, and correlationId without a shared convention.

### 9.3 Do not rely on every header passing across systems

When a message is transferred over HTTP, WebSocket, STOMP, JMS, AMQP, or Kafka, the adapter may map headers to native protocol metadata. Some internal headers may be dropped or represented differently.

If a piece of metadata must reach the consumer, explicitly define how to serialize or map it, test at integration boundaries, and do not rely solely on its presence in MessageHeaders in memory.

## 10. Common Mistakes

- **Confusing payload with headers:** putting business data into metadata makes the schema hard to manage and hard for consumers to understand.
- **Using Message<Object> for all message types:** loses useful type information; use specific types or Message<?> appropriately.
- **Treating headers as a freely mutable map:** MessageHeaders is a read-only structure; create a new message via a builder or accessor.
- **Assuming a message is deeply immutable:** the payload or header values can still reference mutable objects.
- **Copying all headers from input:** may forward untrusted data, internal metadata, or sensitive information.
- **Treating correlation ID as a business identifier:** correlation ID serves to link processing flows; it does not replace an order key or domain identifier.
- **Putting secrets in headers:** metadata may be logged or forwarded across multiple systems.
- **Assuming headers are always preserved across a broker:** adapters may map or drop headers; test metadata propagation.
- **Inconsistent header data types:** one producer sending a number while another sends a string will cause errors when the consumer casts or converts the type.
- **Using headers to replace the payload schema:** consumers will depend on scattered metadata and the contract becomes hard to control.

## 11. Self-Assessment Checklist

You have mastered message structure when you can explain:

- What components does Message<T> consist of?
- How do payload and headers differ in responsibility and usage?
- Why should you declare Message<OrderCreated> instead of always using Message<Object>?
- What standard headers does MessageHeaders provide?
- Why can't you modify the header map directly after a message is created?
- How do MessageBuilder.withPayload and MessageBuilder.fromMessage differ?
- When should you use MessageHeaderAccessor?
- Why is a message envelope only structurally immutable, without guaranteeing deep immutability?
- Why should you not trust tenantId or access permissions just because they appear in an incoming header?
- What can happen to headers when a message passes through an adapter or broker?

When you can create a Message<T>, properly read its payload and metadata, create new messages in a controlled way, and explain the boundaries of headers, you have mastered the data foundation of Spring Messaging.

## 12. Reference Documentation

- Spring Framework Reference Documentation: the Messaging section and the Message, MessageHeaders, and MessageBuilder APIs.
- Javadoc of the org.springframework.messaging package.
- Javadoc of the org.springframework.messaging.support package, especially GenericMessage, MessageBuilder, and MessageHeaderAccessor.
- Spring Integration documentation when you need to learn more about headers and metadata specific to integration flows.

When looking up references, use the documentation for the exact Spring Framework or Spring Boot version of your project. Specific APIs and integration details may change between major versions.