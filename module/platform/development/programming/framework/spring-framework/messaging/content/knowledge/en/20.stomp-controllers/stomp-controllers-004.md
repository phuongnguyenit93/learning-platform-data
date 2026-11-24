# @Payload, Message, MessageHeaders, and Header Accessors

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the payload from the full message envelope in Spring Messaging.
- Choose appropriately among `Message<?>`, `MessageHeaders`, `@Payload`, `@Header`, and `@Headers` in a `@MessageMapping` method.
- Read standard Spring headers, STOMP/Simp session headers, and protocol native headers.
- Create or add headers properly without mutating an immutable `MessageHeaders` directly.
- Recognize common pitfalls when converting payloads, reading headers, and handling client-supplied metadata.

## 1. Where These Types Fit in a STOMP Controller

In a WebSocket application using STOMP, clients send frames to the server. Spring decodes each frame, builds a `Message<?>` object, and routes the message through internal channels. Messages sent to destinations with an application prefix (typically `/app`) can be routed to `@MessageMapping` methods. Destinations meant for the broker (typically `/topic` or `/queue`) are handled by the broker as configured.

A message has two main parts:

1. **Payload**: the business data the client wants to send, such as chat content or order data.
2. **Headers**: metadata describing the message, such as destination, message type, session, content type, message ID, timestamp, and application- or protocol-provided headers.

For example, a simplified STOMP frame might look like this:

```text
SEND
destination:/app/chat.send
content-type:application/json
x-trace-id:req-42

{"text":"Hello"}
```

In this example, the JSON portion is the payload. The `destination`, `content-type`, and `x-trace-id` lines are headers of the frame. When Spring processes the frame, the payload can be converted into a Java DTO; the metadata is represented in the headers of `Message<?>`.

Typical processing flow:

1. The client sends a STOMP `SEND` to `/app/chat.send`.
2. Spring decodes the frame and creates an internal message.
3. A `MessageConverter` converts the payload to the Java type requested by the controller method.
4. Spring resolves the method's parameters: payload, full message, headers, or an accessor.
5. The method executes business logic and may return a result.
6. If `@SendTo` is used, the return value is converted into the payload of a message sent to the specified destination and forwarded through the broker channel.

Key takeaway: `@Payload` focuses on business data; `Message<?>` lets you inspect the entire envelope; header accessors help you read metadata using Spring's or STOMP's exact semantics.

## 2. `Message<T>`: The Full Message Envelope

`org.springframework.messaging.Message<T>` is the interface representing a generic message. It provides two methods:

- `T getPayload()`: returns the payload.
- `MessageHeaders getHeaders()`: returns the message's header collection.

The type parameter `T` describes the payload type at compile time. At runtime, the actual type still depends on how the message was constructed and which converter was used.

Example:

```java
Message<String> message = MessageBuilder.withPayload("hello")
        .setHeader("correlationId", "req-42")
        .build();

String body = message.getPayload();
String correlationId =
        message.getHeaders().get("correlationId", String.class);
```

Here:

- `"hello"` is the payload.
- `"correlationId"` is a custom header.
- `MessageBuilder` creates a new message along with the corresponding headers.

Use `Message<?>` in a controller when you need access to the entire message without coupling to a specific payload type. This is useful for controlled logging, tracing, metadata inspection, or infrastructure-level processing.

`Message<?>` does not replace a business DTO. If a controller needs a strongly typed object for validation and business logic, receive the DTO using `@Payload`. If you need both the DTO and metadata, declare the corresponding parameters together in the same method.

As a general rule, treat a message as an immutable envelope. When you need to change the payload or headers, create a new message using a builder or an appropriate accessor rather than trying to mutate the message currently being processed.

## 3. `@Payload`: Extracting and Converting the Payload

`@Payload` marks the parameter that receives the body of the message. In a STOMP controller, Spring uses a matching `MessageConverter` to convert the payload from its incoming form (such as a byte array or JSON string) into the declared Java type.

Example where the client sends JSON:

```json
{
  "text": "Hello"
}
```

The controller can receive a DTO:

```java
public record ChatRequest(String text) {}

@MessageMapping("/chat.send")
public void send(@Payload ChatRequest request) {
    String text = request.text();
    // Process chat content
}
```

With an appropriate converter configured, the JSON is converted into `ChatRequest` before the method executes. `@Payload` does not parse JSON itself; conversion is the responsibility of `MessageConverter`. The message's content type and the configured converters affect whether conversion succeeds.

In a `@MessageMapping` method, `@Payload` can be omitted if the parameter is not matched by another resolver. Even so, keeping the annotation explicit makes the method signature easier to read and clearly shows which parameter represents business data.

### Combining with Validation

You can use `@Valid` or `@Validated` to ask Spring to validate the DTO after conversion:

```java
public record ChatRequest(
        @NotBlank String text
) {}

@MessageMapping("/chat.send")
public void send(@Valid @Payload ChatRequest request) {
    // Only process when the payload passes validation
}
```

For validation to work, the application needs a Bean Validation implementation and corresponding Spring configuration. In Spring Framework 6 and later, use the `jakarta.validation` namespace; Spring 5 projects typically use `javax.validation`.

Payload validation does not replace access control checks. A structurally valid payload can still contain data that the sender is not permitted to act upon.

## 4. `MessageHeaders`: Reading Message Metadata

`org.springframework.messaging.MessageHeaders` is the collection of headers attached to a message. It implements `Map<String, Object>` so values can be read by key name, but **`MessageHeaders` itself is immutable**. Mutating operations such as `put`, `putAll`, or `remove` are unsupported.

Example of reading headers:

```java
MessageHeaders headers = message.getHeaders();

UUID messageId = headers.getId();
Long timestamp = headers.getTimestamp();

String correlationId =
        headers.get("correlationId", String.class);

Object contentType =
        headers.get(MessageHeaders.CONTENT_TYPE);
```

Some standard headers:

| Header | Meaning |
|---|---|
| `MessageHeaders.ID` | Message ID key; typically a UUID managed by Spring |
| `MessageHeaders.TIMESTAMP` | Creation time of the message, represented as a numeric timestamp |
| `MessageHeaders.CONTENT_TYPE` | Content type, typically represented by `MimeType` |
| `MessageHeaders.REPLY_CHANNEL` | Internal reply channel if used by the message |
| `MessageHeaders.ERROR_CHANNEL` | Internal error channel if used by the message |

ID and timestamp are Spring-managed metadata and belong to the read-only header group by default. Avoid trying to reassign them as ordinary business headers. The ID or timestamp value may be absent in certain specially constructed messages, so handle null cases if logic depends on them.

You can retrieve a value as an expected type using the `get(name, Class<T>)` overload. This avoids manual casting:

```java
String tenantId = headers.get("tenant-id", String.class);
Integer priority = headers.get("priority", Integer.class);
```

If the header does not exist or its value type is incompatible, the result may be `null`. Never assume every header is always present or that every value is a string.

In Spring Messaging, headers may also hold metadata specific to Spring, the transport, or the application. With STOMP, it is important to distinguish Spring's internal headers from native headers preserved from the original frame; the next section explains this distinction.

## 5. Header Accessors and Their Scopes

A header accessor wraps headers, provides semantically clear getters/setters, and manages mutable/immutable state. The main classes form the following inheritance hierarchy:

```text
MessageHeaderAccessor
    └── NativeMessageHeaderAccessor
            └── SimpMessageHeaderAccessor
                    └── StompHeaderAccessor
```

| Accessor | Scope | When to Use |
|---|---|---|
| `MessageHeaderAccessor` | General Spring Messaging headers | Reading or creating general headers, protocol-agnostic message handling |
| `NativeMessageHeaderAccessor` | Native headers from external systems | Base class for storing and accessing native headers; usually used indirectly via a specialized accessor |
| `SimpMessageHeaderAccessor` | Common Simple Messaging metadata | Reading destination, message type, session ID, session attributes, subscription ID, and user |
| `StompHeaderAccessor` | STOMP-specific metadata | Reading STOMP commands and native headers from STOMP frames |

### 5.1. `MessageHeaderAccessor`

This is the general-purpose accessor. Common operations include:

- `getHeader(name)`: reads a header.
- `setHeader(name, value)`: sets or replaces a header value.
- `setHeaderIfAbsent(name, value)`: sets the header only if it does not already have a value.
- `removeHeader(name)`: removes a header.
- `getMessageHeaders()`: retrieves the underlying `MessageHeaders` object.
- `getMutableAccessor(message)`: obtains a mutable accessor based on an existing message.

Use an accessor when you need to manipulate headers in a controlled way. If you only need to create a new message with a few headers, `MessageBuilder` is usually shorter and easier to read.

### 5.2. `NativeMessageHeaderAccessor`

Headers arriving from an external protocol or system are stored separately in a native headers section under the `NATIVE_HEADERS` key. The data supports multiple values per header name, equivalent to `Map<String, List<String>>`.

Important methods:

- `getNativeHeader(name)`: retrieves the list of all values for a native header.
- `getFirstNativeHeader(name)`: retrieves the first value.
- `setNativeHeader(name, value)`: replaces existing values with a single value.
- `addNativeHeader(name, value)`: appends a value to the existing list.

A native header can appear multiple times in a single frame. Therefore, if you need all values, use `getNativeHeader` instead of taking only the first value.

`NativeMessageHeaderAccessor` is typically used through a protocol-specific subclass. For STOMP, the appropriate class is `StompHeaderAccessor`.

### 5.3. `SimpMessageHeaderAccessor`

`SimpMessageHeaderAccessor` provides uniform access to metadata for simple messaging protocols. Commonly read details include:

- `getDestination()`: the destination associated with the message.
- `getMessageType()`: the Simp message type, such as message, subscribe, or unsubscribe.
- `getSessionId()`: the ID of the current session.
- `getSessionAttributes()`: map of attributes attached to the session.
- `getSubscriptionId()`: the subscription ID, if present.
- `getUser()`: the `Principal` attached to the session, if established.

Example:

```java
@MessageMapping("/chat.inspect")
public void inspect(SimpMessageHeaderAccessor headers) {
    String destination = headers.getDestination();
    String sessionId = headers.getSessionId();
    Principal user = headers.getUser();

    // Use metadata for logging or appropriate business logic
}
```

This accessor is suitable when logic needs the session or destination without depending directly on STOMP syntax.

### 5.4. `StompHeaderAccessor`

`StompHeaderAccessor` extends `SimpMessageHeaderAccessor` and adds STOMP-specific details. Useful methods include:

- `getCommand()`: retrieves the STOMP command, such as `SEND`, `SUBSCRIBE`, or `DISCONNECT`.
- `getReceipt()` and `getReceiptId()`: accesses receipt information.
- `getVersion()`: retrieves the STOMP version, if present.
- `getFirstNativeHeader(name)`: retrieves the first value of a native header.
- `getNativeHeader(name)`: retrieves all values of a native header.

Example of reading custom headers sent by a client:

```java
@MessageMapping("/chat.inspect")
public void inspect(StompHeaderAccessor headers) {
    StompCommand command = headers.getCommand();
    String traceId = headers.getFirstNativeHeader("x-trace-id");
    List<String> tags = headers.getNativeHeader("x-tag");

    // Inspect command, traceId, or tags as needed
}
```

Raw STOMP headers are kept in the native headers area; certain metadata used for general processing is mapped into Simp headers. Thus, when you need the destination or session ID, use getters on `SimpMessageHeaderAccessor`; when you need the STOMP command or raw STOMP headers, use `StompHeaderAccessor`.

## 6. Controller Example Combining Payload, Message, and Accessors

The example below illustrates a chat controller that receives a converted and validated DTO while reading metadata from the envelope and STOMP frame.

```java
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(
            @Valid @Payload ChatRequest request,
            Message<?> message,
            MessageHeaders headers,
            SimpMessageHeaderAccessor simpHeaders,
            StompHeaderAccessor stompHeaders) {

        String traceId =
                stompHeaders.getFirstNativeHeader("x-trace-id");

        return new ChatEvent(
                request.text(),
                simpHeaders.getDestination(),
                simpHeaders.getSessionId(),
                traceId,
                message.getHeaders().getId(),
                headers.getTimestamp()
        );
    }
}

record ChatRequest(@NotBlank String text) {}

record ChatEvent(
        String text,
        String inboundDestination,
        String sessionId,
        String traceId,
        UUID messageId,
        Long receivedAt
) {}
```

How to read the example:

1. `@Payload` instructs Spring to convert the payload into `ChatRequest`.
2. `@Valid` triggers Bean Validation for the DTO, provided the application has configured a validation provider.
3. `Message<?>` provides the entire envelope; here we read the message ID from the message's headers.
4. `MessageHeaders` provides metadata in map form; for example, reading the timestamp.
5. `SimpMessageHeaderAccessor` reads the destination and session ID using Spring messaging semantics.
6. `StompHeaderAccessor` reads the `x-trace-id` native header from the STOMP frame.
7. `@SendTo` routes the return value to `/topic/chat`. Spring uses an appropriate message converter to turn the `ChatEvent` object into the outbound payload.

This is an integrated controller snippet for an application already configured with WebSocket/STOMP, message converters, and validation. This snippet alone is not a standalone program to run directly with `javac`.

## 7. Creating Messages and Adding Headers Properly

Never mutate `MessageHeaders` directly. Use `MessageBuilder` to create a new message:

```java
Message<String> outgoing = MessageBuilder.withPayload("ping")
        .setHeader("correlationId", "req-42")
        .setHeaderIfAbsent("source", "chat-controller")
        .build();
```

If you need to use the general accessor to build headers:

```java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("correlationId", "req-42");

Message<String> outgoing = MessageBuilder.createMessage(
        "ping",
        accessor.getMessageHeaders()
);
```

By default, when `getMessageHeaders()` is called, the accessor transitions the headers to an immutable state and can no longer modify them through that accessor. This behavior is intentional to prevent unintended metadata changes after a message has been created.

You can call `setLeaveMutable(true)` if a message-initialization pipeline within the same flow genuinely needs to keep headers mutable across multiple steps. When finished, you must call `setImmutable()` to lock the headers. This is an advanced mechanism; in normal processing flows, prefer building a complete message with `MessageBuilder`.

If you need to enrich an existing message, create a new message and set headers on the builder rather than calling `put` on the original message's headers:

```java
Message<?> enriched = MessageBuilder.fromMessage(inbound)
        .setHeaderIfAbsent("correlationId", "req-42")
        .build();
```

The new message is a new envelope. Check the retention or regeneration policy for metadata such as ID/timestamp in your Spring version if business logic depends on them.

## 8. Which Parameter Should You Choose in a Controller?

| Need | Recommended Parameter | Reason |
|---|---|---|
| Receive a converted business DTO | `@Payload MyDto` | Strongly typed, supports message conversion and validation |
| Inspect the entire envelope | `Message<?>` | Includes both payload and headers |
| Read multiple general metadata fields | `MessageHeaders` | Accesses headers as an immutable map |
| Read a single header | `@Header("headerName")` | Concise signature, can request type conversion |
| Read all headers as a map | `@Headers Map<String, Object>` | Suitable when iterating over the header set |
| Read session, destination, user | `SimpMessageHeaderAccessor` | Getters with clear messaging semantics |
| Read STOMP command or native STOMP header | `StompHeaderAccessor` | Accesses STOMP-specific metadata |
| Create or add headers | `MessageBuilder` or `MessageHeaderAccessor` | Manages mutable/immutable state properly |

There is no need to declare every parameter type in every handler. Accept only what the method actually needs. A concise signature lets readers immediately see the boundary between business data and transport metadata.

## 9. Security and Reliability Notes

- **Treat payloads and native headers from clients as untrusted input.** Validate format, size, allowed values, and permission to perform the operation.
- **Never use client-supplied headers to determine identity or permissions.** Do not trust values such as `x-user-id`, `role`, or `isAdmin`. Use the authenticated `Principal` and Spring Security mechanisms.
- **Do not confuse session ID with user ID.** A user can have multiple sessions; a session ID identifies only one connection session.
- **Handle optional headers.** Headers may be absent; use optional parameters or check for null before using them.
- **Limit logging.** Never log passcodes, tokens, personal information, or full sensitive payloads. Log only trace IDs and strictly necessary metadata.
- **Do not put business logic in transport headers.** Data such as message text, quantities, or order status belongs in the payload/DTO. Headers are better suited for correlation IDs, trace IDs, content types, or routing metadata.
- **Use an accessor matching the abstraction level.** Prefer the Simp accessor for general metadata; use the STOMP accessor only when protocol details are needed.

## 10. Common Pitfalls

| Error | Cause | How to Fix |
|---|---|---|
| Calling `headers.put(...)` | `MessageHeaders` is immutable | Use `MessageBuilder` or `MessageHeaderAccessor` |
| Failing to read `x-trace-id` via normal map key | It is a native STOMP header, stored inside the native headers section | Use `StompHeaderAccessor.getFirstNativeHeader(...)` |
| Reading only the first value when a header has multiple values | Native headers can store multiple values | Use `getNativeHeader(...)` to get the list |
| `@Payload` fails to convert JSON to DTO | Missing or incompatible converter, or wrong content type | Check configured converters and the message's content type |
| Assuming a header always exists | Optional headers may be missing | Use `required = false` with `@Header` or check for null |
| Trying to modify an accessor after calling `getMessageHeaders()` | The accessor locks headers by default | Finish edits before retrieving headers; only use `setLeaveMutable(true)` with clear reason |
| Using client-sent headers for authorization | Clients can set arbitrary header values | Use authentication info from Spring Security/`Principal` |
| Treating session ID as user identity | A session represents only a single connection | Use `Principal` to identify the user |

A notable pitfall in STOMP is confusing raw protocol headers with Spring's internal processing headers. If you need the exact value sent by the client, inspect native headers using the specialized accessor. If you need routing/session information managed by Spring, use the corresponding Simp getters.

## 11. Self-Check Exercise

A client sends a STOMP `SEND` to `/app/orders.submit` with JSON containing `orderId` and `quantity`, along with a native header `x-correlation-id`. The handler must:

- Receive a strongly typed DTO with validation.
- Read the session ID.
- Read the correlation ID.
- Never use client-sent headers to decide whether the user is allowed to modify the order.

An appropriate signature:

```java
@MessageMapping("/orders.submit")
public void submit(
        @Valid @Payload OrderRequest request,
        SimpMessageHeaderAccessor simpHeaders,
        StompHeaderAccessor stompHeaders) {

    String sessionId = simpHeaders.getSessionId();
    String correlationId =
            stompHeaders.getFirstNativeHeader("x-correlation-id");

    // Check authorization using Principal/Spring Security at the appropriate layer.
    // Then process the request using orderId and quantity.
}

record OrderRequest(
        @NotBlank String orderId,
        @Positive int quantity
) {}
```

Answer these questions for yourself:

1. Why is `@Payload OrderRequest` more suitable than `Message<?>` if the handler primarily processes order data?
2. Why is `x-correlation-id` read via `StompHeaderAccessor`?
3. Why can't `put` be called on `MessageHeaders`?
4. If the handler needs both the payload and the session ID, can it declare both `@Payload` and `SimpMessageHeaderAccessor`?

Answers:

1. A DTO represents the business structure and enables typed validation.
2. It is a native header sent in the STOMP frame.
3. `MessageHeaders` is designed to be immutable; create a new message when changes are needed.
4. Yes. Spring supports combining these parameter types in a `@MessageMapping` signature.

## 12. Key Takeaways

- `Message<T>` is an envelope consisting of a payload and headers.
- `@Payload` receives the payload converted by a `MessageConverter`; `@Valid` can trigger validation.
- `MessageHeaders` is an immutable map with `Object` values.
- `MessageHeaderAccessor` manages reading/writing headers; `NativeMessageHeaderAccessor` holds headers from the transport.
- `SimpMessageHeaderAccessor` reads common messaging metadata; `StompHeaderAccessor` reads STOMP commands and native headers.
- Use `MessageBuilder` to safely create new messages or add headers.
- Treat all client payloads and native headers as input requiring validation; use the authenticated identity for authorization.

## References

- Spring Framework Reference — [Annotated Controllers](https://docs.spring.io/spring/reference/web/websocket/stomp/handle-annotations.html)
- Spring Framework Reference — [Flow of Messages](https://docs.spring.io/spring/reference/web/websocket/stomp/message-flow.html)
- Spring Framework Javadoc — [Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- Spring Framework Javadoc — [MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- Spring Framework Javadoc — [MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- Spring Framework Javadoc — [NativeMessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html)
- Spring Framework Javadoc — [SimpMessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessageHeaderAccessor.html)
- Spring Framework Javadoc — [StompHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
