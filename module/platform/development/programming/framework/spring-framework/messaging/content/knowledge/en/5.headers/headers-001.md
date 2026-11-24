# MessageHeaders and Accessing Message Metadata

## Objectives

In Spring Messaging, the payload contains the primary business data, while headers contain metadata describing how a message is created, tracked, routed, or processed. Knowing how to read and build headers helps components communicate without stuffing transport information into the payload.

After this lesson, you will be able to:

- Explain the role of `MessageHeaders` in a `Message`.
- Safely read headers by name or data type.
- Create and copy headers using `MessageBuilder`.
- Distinguish immutable `MessageHeaders` from `MessageHeaderAccessor` used to modify metadata during the message construction phase.
- Use `@Header` and `@Headers` to receive metadata in handlers.
- Recognize Spring Messaging, Spring Integration, and external protocol headers.
- Avoid pitfalls when copying, sending across a broker, logging, or handling untrusted data.

## 1. A Message Consists of Payload and Headers

Spring represents a message with the `Message<T>` interface. A message has two parts:

- **Payload:** the main content, such as `OrderCreated`, a text string, a byte array, or a business object.
- **Headers:** a set of `String → Object` key–value pairs that provide metadata accompanying the payload.

Conceptual example:

~~~text
Message<OrderCreated>
  payload:
    orderId = "ORD-42"
    total = 250000

  headers:
    id = 4c1...
    timestamp = 1794020000000
    contentType = application/json
    traceId = "trace-2026-001"
    source = "checkout-service"
~~~

The payload answers the question “what data does the message carry?”. Headers answer “what information does the message carry for the system to track, route, or process it?”.

Some examples:

- `traceId`: links logs/spans of the same request across multiple services.
- `correlationId`: links a request with its reply or links messages belonging to the same business workflow.
- `contentType`: describes the content format, such as JSON or plain text.
- `replyChannel`: the reply destination in a Spring request/reply flow.
- `priority`: priority level when a channel or adapter supports priority-based processing.

Not every header is used by every module. The meaning of a header depends on the active API, channel, adapter, and protocol.

## 2. What Is MessageHeaders?

`org.springframework.messaging.MessageHeaders` is the class that holds a message's headers. It implements `Map<String, Object>`, so it can be read using familiar Map operations:

~~~java
MessageHeaders headers = message.getHeaders();

Object traceId = headers.get("traceId");
boolean hasTenant = headers.containsKey("tenantId");
Set<String> names = headers.keySet();
~~~

However, `MessageHeaders` is **immutable**. Map mutating operations such as `put`, `putAll`, `remove`, or `clear` will throw `UnsupportedOperationException`.

~~~java
// Invalid: MessageHeaders does not allow direct modification.
message.getHeaders().put("traceId", "new-value");
~~~

To add, replace, or remove headers, create a new message with `MessageBuilder` or use `MessageHeaderAccessor`. This immutable design allows a message to be passed across multiple components without its metadata being arbitrarily altered by a consumer.

Note: the immutability of `MessageHeaders` applies to the Map structure. If you place a mutable object into a header, that object can still be mutated through its reference. Therefore, prefer immutable values such as `String`, numbers, `UUID`, `MimeType`, or simple data types with a clear contract.

## 3. Standard Spring Messaging Headers

`MessageHeaders` defines the core header name constants:

| Constant | Meaning | Common type/value |
|---|---|---|
| `MessageHeaders.ID` | Message identifier | Automatically generated `UUID` |
| `MessageHeaders.TIMESTAMP` | Message creation time | `Long` |
| `MessageHeaders.CONTENT_TYPE` | Payload content type | `MimeType`, e.g. `application/json` |
| `MessageHeaders.REPLY_CHANNEL` | Destination for replies | `MessageChannel` or channel name depending on configuration |
| `MessageHeaders.ERROR_CHANNEL` | Destination for errors in a messaging flow | `MessageChannel` or channel name depending on configuration |

### ID and timestamp

When creating `MessageHeaders`, Spring automatically adds an ID and timestamp. The default ID is a UUID. These are framework-managed metadata:

- Do not manually set `MessageHeaders.ID` as a business ID.
- Do not use the message ID as a substitute for an order ID, event ID, or correlation ID.
- Do not overwrite ID/timestamp when copying headers with `MessageBuilder`; these values are protected and the new message receives newly generated metadata according to the framework's mechanism.
- If the business logic needs the time an event actually occurred, create a separate header such as `occurredAt` or place the business timestamp in the payload. The message timestamp is when the message was created in the application, not necessarily when the business event happened.

ID answers “which message instance is this?”. Correlation ID answers “which request or workflow does this message belong to?”. Trace ID answers “which trace do these distributed operations belong to?”. These three values can differ and should not be used interchangeably.

### Content type

`CONTENT_TYPE` describes the content format. For example:

~~~java
.setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
~~~

Or use `MessageHeaderAccessor.setContentType(MimeType)`.

This header is metadata so converters or adapters can choose an appropriate way to handle the payload. Simply setting `application/json` does not automatically turn a Java object into JSON; conversion still depends on the `MessageConverter`, serializer, and transport configuration.

### Reply channel and error channel

These two headers support several processing models in Spring:

- `REPLY_CHANNEL` indicates where to send the reply result.
- `ERROR_CHANNEL` indicates where to route error messages in a flow configured with error handling.

The value can be a channel object or a channel name, depending on the API. An in-memory `MessageChannel` usually only has meaning within the application. When a message passes through a broker or is serialized, do not assume a local channel object can be transmitted as-is to another process. For distributed systems, use addresses or reply/routing mechanisms supported by the protocol and adapter.

## 4. Reading Headers and Type Checking

Values can be read in two ways:

~~~java
Object raw = headers.get("retryCount");
Integer retryCount = headers.get("retryCount", Integer.class);
~~~

The second approach expresses the expected data type directly at the call site. It is not an arbitrary conversion mechanism from string to number. Producer and consumer must agree on the header's type.

Some useful operations:

~~~java
String traceId = headers.get("traceId", String.class);

if (headers.containsKey("tenantId")) {
    String tenantId = headers.get("tenantId", String.class);
}

Object replyChannel = headers.getReplyChannel();
UUID messageId = headers.getId();
Long createdAt = headers.getTimestamp();
~~~

When a header may be absent, handle the `null` case:

~~~java
String traceId = headers.get("traceId", String.class);
if (traceId == null || traceId.isBlank()) {
    // Use a fallback or reject the message according to business rules.
}
~~~

Do not cast directly without checking the data contract:

~~~java
// Prone to ClassCastException if the producer sends retryCount as a String.
Integer retryCount = (Integer) headers.get("retryCount");
~~~

Clearly specify a header's name, data type, unit of measurement, default value, and meaning. For example, `timeoutMs` is clearer than `timeout` if the value is in milliseconds.

## 5. Creating Messages and Attaching Metadata with MessageBuilder

The common way to create a message is `MessageBuilder.withPayload(...)`. The builder lets you add, replace, or remove headers before calling `build()`.

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("traceId", "trace-2026-001")
        .setHeader("source", "checkout-service")
        .setHeader("tenantId", "tenant-a")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Some important methods:

| Method | Behavior |
|---|---|
| `setHeader(name, value)` | Adds or replaces a header value. If value is `null`, that header is removed. |
| `setHeaderIfAbsent(name, value)` | Sets only if the header does not already have a value. |
| `copyHeaders(map)` | Copies key–value pairs; existing values may be overwritten. ID and timestamp remain protected. |
| `copyHeadersIfAbsent(map)` | Copies only headers that do not yet exist, without overwriting existing values. |
| `removeHeader(name)` | Removes a header from the new message being built. |
| `removeHeaders(patterns)` | Removes headers matching supported name patterns. |
| `build()` | Creates a new message with the configured payload and headers. |

Example illustrating the difference between overwriting copy and copy-if-absent:

~~~java
Map<String, Object> incoming = Map.of(
        "traceId", "trace-from-upstream",
        "source", "gateway"
);

Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("traceId", "trace-created-here")
        .copyHeaders(incoming)
        .build();

// traceId = "trace-from-upstream"
// source  = "gateway"
~~~

If `copyHeaders(incoming)` is changed to `copyHeadersIfAbsent(incoming)`, the previously set `traceId` remains `trace-created-here`.

To create a new message from an existing message:

~~~java
Message<String> enriched = MessageBuilder.fromMessage(message)
        .setHeader("processedBy", "order-handler")
        .build();
~~~

`fromMessage` initializes a builder with the payload and headers copied from the original message. This is still a new message; ID and timestamp are managed by the framework, while business metadata such as trace ID or correlation ID are typically preserved unless explicitly changed.

## 6. MessageHeaderAccessor: Controlled Access and Modification of Headers

`MessageHeaderAccessor` is a wrapper around `MessageHeaders` that provides a typed API and a mechanism for managing mutable/immutable state.

Use the accessor when:

- You want to build multiple headers step by step.
- You want to update or remove headers via an API rather than modifying a Map.
- You want to use typed methods such as `setContentType`, `setReplyChannel`, `setErrorChannel`.
- You want to retrieve the accessor attached to a message within a flow that still preserves the accessor metadata.

Example creating a message via an accessor:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("traceId", "trace-2026-001");
accessor.setHeader("tenantId", "tenant-a");
accessor.setContentType(MimeTypeUtils.APPLICATION_JSON);

MessageHeaders headers = accessor.getMessageHeaders();
Message<String> message = MessageBuilder.createMessage("order-42", headers);
~~~

By default, when `getMessageHeaders()` is called, the accessor finalizes header construction and prevents further modifications through that accessor. This is the default way to produce a message with immutable headers.

### When is setLeaveMutable(true) needed?

In some flows, an application needs to instantiate the message first and then finalize metadata within the same processing phase. You can call:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("traceId", "trace-2026-001");
accessor.setLeaveMutable(true);

Message<String> message = MessageBuilder.createMessage(
        "order-42",
        accessor.getMessageHeaders()
);

// During the initialization phase on the same thread:
MessageHeaderAccessor current = MessageHeaderAccessor.getAccessor(message);
if (current != null && current.isMutable()) {
    current.setHeader("processedBy", "order-handler");
    current.setImmutable();
}
~~~

`setLeaveMutable(true)` keeps headers modifiable via the accessor after the message is created. When finished, call `setImmutable()` to lock modifications.

This mechanism is designed for the initialization phase within the same thread. Do not distribute a message with mutable headers across multiple threads or let multiple components modify it concurrently. If a message is already immutable, create a new mutable accessor with `MessageHeaderAccessor.getMutableAccessor(message)`, update it, and then create a new message with those headers.

`MessageHeaderAccessor.getAccessor(message)` may return `null` if the original accessor is no longer attached to the message or was not preserved across processing steps. Therefore, do not assume every message received from a broker can restore its original accessor.

### Methods to remember

| Method | Purpose |
|---|---|
| `setHeader(name, value)` | Adds/replaces a header; a null value removes the header. |
| `setHeaderIfAbsent(name, value)` | Sets only if no value exists yet. |
| `getHeader(name)` | Reads a header value. |
| `removeHeader(name)` | Removes a header. |
| `removeHeaders(patterns)` | Removes headers by name patterns. |
| `copyHeaders(map)` | Copies and overwrites headers with matching names. |
| `copyHeadersIfAbsent(map)` | Copies while preserving existing values. |
| `getMessageHeaders()` | Gets the current MessageHeaders; by default finalizes and locks the accessor. |
| `setLeaveMutable(true)` | Keeps headers editable via the accessor after retrieving MessageHeaders. |
| `setImmutable()` | Ends the editing phase. |
| `getMutableAccessor(message)` | Creates a mutable accessor to update an existing message. |
| `toMap()` | Returns a copy of the headers as a Map. |

## 7. Receiving Headers in Handlers with @Header and @Headers

In Spring-supported messaging handlers, metadata can be bound directly to method parameters.

- `@Header("traceId")` retrieves a specific header.
- `@Headers` binds all headers into a `Map<String, Object>`.
- `@Payload` explicitly marks the parameter receiving the payload.

Illustrative example of a Spring Messaging/WebSocket handler:

~~~java
@MessageMapping("/orders")
public void handleOrder(
        @Payload OrderCreated order,
        @Header("traceId") String traceId,
        @Header(value = "tenantId", required = false) String tenantId,
        @Headers Map<String, Object> allHeaders) {

    System.out.println("orderId=" + order.orderId());
    System.out.println("traceId=" + traceId);
    System.out.println("tenantId=" + tenantId);
}
~~~

This is an illustrative handler snippet; it requires the corresponding messaging endpoint configuration. `@Header` defaults to `required=true`. If a header may be missing, set `required=false` or provide a `defaultValue`. `@Headers` requires a parameter type compatible with `Map<String, Object>`.

There is no need to accept the entire `Message<?>` if the method only needs the payload and a few pieces of metadata. Using specific parameters makes the contract expected by the handler explicit.

## 8. Spring Messaging, Spring Integration, and Protocol Headers

Not all headers are defined by `MessageHeaders`. It is important to distinguish the source of metadata:

| Group | Examples | Where defined |
|---|---|---|
| Core headers | ID, TIMESTAMP, CONTENT_TYPE, REPLY_CHANNEL, ERROR_CHANNEL | Spring Messaging: `MessageHeaders` |
| Custom headers | traceId, tenantId, source, eventType | Application convention |
| Spring Integration headers | CORRELATION_ID, SEQUENCE_NUMBER, SEQUENCE_SIZE, PRIORITY, EXPIRATION_DATE | `IntegrationMessageHeaderAccessor` |
| Protocol/adapter headers | JMS properties, AMQP headers, Kafka record headers, STOMP native headers | Corresponding integration module or protocol |

For example, Spring Integration has `IntegrationMessageHeaderAccessor.CORRELATION_ID` and headers for message grouping such as `SEQUENCE_NUMBER` and `SEQUENCE_SIZE`. Those constants belong to Spring Integration, not the core header list of `MessageHeaders`.

For WebSocket/STOMP, classes like `SimpMessageHeaderAccessor` and `StompHeaderAccessor` provide specialized APIs for working with session metadata and native STOMP headers. For JMS, AMQP, or Kafka, the corresponding module may provide its own constants and mappers.

When a message passes through an adapter or broker, internal Spring headers may be mapped to protocol metadata. Mapping depends on the mapper and protocol limitations:

- Some headers may be renamed or type-converted.
- Some internal headers have no corresponding representation on the wire.
- Headers with custom Java object values may not be serializable.
- Protocols may restrict data types, sizes, or header names.

Do not assume the entire `MessageHeaders` will automatically pass through a broker and arrive intact at the consumer. Configure header mappers/serializers and test with real messages.

## 9. Copying and Propagating Headers in a Flow

When a component receives a message and creates a new message, it must decide which metadata to retain.

There are three common approaches:

1. **Create a new message from scratch:** only set the headers owned by the current component.
2. **Copy from the input message:** use `MessageBuilder.fromMessage` or `copyHeaders` when metadata needs to be preserved.
3. **Conditional copy:** use `copyHeadersIfAbsent` to preserve values already set by a previous component.

In Spring Integration, many message-producing endpoints have a mechanism to forward inbound headers to the outbound message. Headers already present on the outbound message may take precedence; some endpoints allow configuring header patterns that should not be forwarded. If a transformer returns a complete `Message`, the transformer code is responsible for that message's headers. This is a rule of Spring Integration endpoints/flows, not a universal guarantee for every broker or every Spring module.

Establish clear policies for header groups:

- **Keep:** trace ID, correlation ID, tenant ID if still within the proper scope.
- **Create new:** message ID, timestamp, or information about the component that just processed it.
- **Remove:** internal data that is no longer meaningful, headers used only for the prior step, or information not permitted to cross a different trust boundary.

Do not copy every header blindly. A header created in an HTTP request or in an inbound adapter may not be appropriate when publishing a public event.

## 10. Designing Good Custom Headers

A custom header should have a clear contract:

| Attribute | Example |
|---|---|
| Name | `traceId`, `tenantId`, `eventType` |
| Type | `String`, `UUID`, `Integer`, `MimeType` |
| Meaning | Correlation ID, processing tenant, event type |
| Owner | Which producer creates it and which components may modify it |
| Scope | Internal to one service, one flow, or across a broker |
| Missing-value rule | Required, optional, or has a default |
| Propagation rule | Keep, replace, map, or drop at which adapters |

Some principles:

- Use consistent names and avoid colliding with standard or adapter headers. In large systems, prefixes such as `acme.traceId` can be used.
- Specify the data type and unit of measurement. Use `timeoutMs` instead of an ambiguous name like `timeout`.
- Prefer `String`, numbers, boolean, `UUID`, or simple types that serialize cleanly.
- Keep correlation ID stable throughout the workflow; do not regenerate it in every handler if the goal is to link requests with replies.
- Do not use headers to replace the business payload. If the consumer needs data to execute business logic, that data usually belongs in the payload.
- Do not use headers to store passwords, access tokens, secrets, or sensitive data. Headers can be logged, copied, and passed through many adapters.
- Treat any header received from external sources as untrusted data. Validate type, length, allowed values, and authorization before routing or granting access.

## 11. Logging and Metadata Security

Headers are helpful for observability, but logging all headers can leak information or bloat logs.

You should:

- Log trace ID, correlation ID, and message ID when useful for investigation.
- Mask or strip authorization tokens, cookies, credentials, and personal data.
- Limit the length of headers supplied by external clients.
- Do not rely solely on client-supplied headers to authenticate identity or authorize access.
- Do not log sensitive payloads/headers at DEBUG level in production without a redaction policy.
- Avoid putting complex objects into headers because `toString()` or serialization can bloat logs or expose data.

A trace ID helps correlate logs across multiple services, but it does not prove a message is valid or came from a trusted sender.

## 12. Runnable Java 17+ Example

The example below creates a message, adds custom headers, sets the content type, and reads metadata using the typed API. It only uses the `spring-messaging` module and does not require a broker.

Project structure:

~~~text
message-headers-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageHeadersDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-headers-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
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
        </plugins>
    </build>
</project>
~~~

### MessageHeadersDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

public class MessageHeadersDemo {

    public static void main(String[] args) {
        Message<String> message = MessageBuilder.withPayload("order-42")
                .setHeader("traceId", "trace-2026-001")
                .setHeader("tenantId", "tenant-a")
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
                .build();

        MessageHeaders headers = message.getHeaders();

        System.out.println("payload=" + message.getPayload());
        System.out.println("traceId=" + headers.get("traceId", String.class));
        System.out.println("tenantId=" + headers.get("tenantId", String.class));
        System.out.println("contentType="
                + headers.get(MessageHeaders.CONTENT_TYPE, MimeType.class));
        System.out.println("idPresent=" + (headers.getId() != null));
        System.out.println("timestampPresent=" + (headers.getTimestamp() != null));
    }
}
~~~

Run from the project directory with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageHeadersDemo
~~~

Stdout output:

~~~text
payload=order-42
traceId=trace-2026-001
tenantId=tenant-a
contentType=text/plain
idPresent=true
timestampPresent=true
~~~

The actual ID and timestamp change each time a message is created, but the program only prints whether they exist, so stdout remains deterministic.

### Reading and enriching a message with MessageHeaderAccessor

The following snippet illustrates updating metadata on an existing message. This is a standalone snippet for API reference; the Maven project above does not need this snippet added to `main` yet.

~~~java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(message);

accessor.setHeader("processedBy", "order-handler");

Message<String> enriched = MessageBuilder.createMessage(
        message.getPayload(),
        accessor.getMessageHeaders()
);
~~~

The accessor creates an editable header area. `createMessage` creates a new message using the updated headers. If managing mutable state manually with `setLeaveMutable(true)`, call `setImmutable()` when finished and before sharing the message with another component or thread.

## 13. Common Pitfalls

| Error | Cause | Resolution |
|---|---|---|
| `UnsupportedOperationException` when calling `put` or `remove` | Modifying `MessageHeaders` directly. | Use `MessageBuilder` or `MessageHeaderAccessor`. |
| `ClassCastException` when reading a header | Producer and consumer do not agree on the type. | Standardize the header type and read using `get(name, Type.class)`. |
| Header lost after broker | Adapter does not map that header or the protocol does not support the data type. | Check header mapper, serializer, and protocol constraints. |
| Old header overwrites new header | Using `copyHeaders` after setting the new value. | Change the order or use `copyHeadersIfAbsent`. |
| Trace ID changes between steps | Generating a new trace ID in every handler or failing to copy headers. | Define a forwarding policy for trace/correlation IDs. |
| Unable to retrieve accessor | Message no longer retains the original accessor or passed through serialization/adapter. | Use `getMutableAccessor(message)` to create a new accessor. |
| Missing header causes handler failure | `@Header` requires the header to be present by default. | Use `required=false`, `defaultValue`, or verify the producer contract. |
| Logs contain tokens or private data | Logging all headers without filtering. | Redact or allowlist headers permitted for logging. |

## 14. Header Design Checklist

- [ ] Payload and metadata are separated according to their purposes.
- [ ] Header names follow a convention and do not collide.
- [ ] Each header has a clear data type, unit, and meaning.
- [ ] Spring's ID/timestamp are left to framework management.
- [ ] Correlation ID and trace ID are propagated appropriately across the workflow.
- [ ] Potentially missing headers are handled explicitly.
- [ ] Headers are copied intentionally, not copied wholesale mechanically.
- [ ] Header mappers and serializers have been verified at broker boundaries.
- [ ] Messages are not shared in a mutable state outside the initialization phase.
- [ ] Logs do not contain tokens, credentials, or sensitive data.
- [ ] Headers from external sources are validated before being used for routing or authorization.

## Key Takeaways

- `MessageHeaders` is a metadata Map, but it is **immutable**.
- Spring automatically manages `ID` and `TIMESTAMP`; do not use them as business IDs or correlation IDs.
- Use `MessageBuilder` to create new messages and copy headers intentionally.
- Use `MessageHeaderAccessor` to read/write headers via a controlled API; by default, the accessor locks headers when retrieving `MessageHeaders`.
- `@Header` receives a specific piece of metadata; `@Headers` receives a Map containing all headers.
- Core headers, Spring Integration headers, and native protocol headers belong to different groups.
- When crossing a broker, headers must be mapped and serialized per protocol; not every header is propagated automatically.

## Official Documentation

- [Spring Framework Javadoc: MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework Javadoc: MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework Javadoc: MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework Javadoc: @Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html)
- [Spring Framework Javadoc: @Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html)
- [Spring Integration Reference: Message and Message Headers](https://docs.spring.io/spring-integration/reference/message.html)
- [Spring Integration Reference: Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html)
