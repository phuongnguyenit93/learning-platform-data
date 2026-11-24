# MessageHeaderAccessor and Managing Mutable State in Spring Messaging

## 1. Objective: Controlled Metadata Modification

In Spring Messaging, a message consists of a payload and headers. The payload holds the primary data; headers carry metadata such as correlation ID, content type, destination, session information, or routing data.

Headers are normally treated as immutable data once a message has been created. This approach allows a message to be passed across multiple handlers, channels, and threads without worrying that one component might unexpectedly alter metadata that another component is reading.

However, while building or enriching a message, an application sometimes needs to add, replace, or remove a header. **MessageHeaderAccessor** provides an API to do this with a clear lifecycle: create an accessor, modify metadata, build the message, and then pass the message along for processing.

After this lesson, you should be able to:

- Distinguish MessageHeaders from MessageHeaderAccessor.
- Explain why headers of an emitted message should be treated as immutable.
- Create messages with custom headers and modify metadata of an existing message using an accessor.
- Use specialized accessors when working with STOMP or Spring messaging headers.
- Understand the impact of mutable state on interceptors, multiple subscribers, and multithreaded processing.
- Avoid directly mutating the headers map, sharing mutable state, or trusting client-sent metadata.

## 2. MessageHeaders and MessageHeaderAccessor Have Different Roles

### 2.1 MessageHeaders: The Headers Part of a Message

`MessageHeaders` is the data type holding metadata attached to a message. It implements the Map interface for reading by header name, for example:

~~~java
Object correlationId = message.getHeaders().get("app.correlationId");
~~~

Direct map-updating operations are not a supported way to modify a message. `MessageHeaders` is designed to provide a read-only view after the message is created. For instance, calling `put` or `remove` directly on the headers map typically results in an `UnsupportedOperationException`.

This design is useful because a message may be shared across multiple components. If one subscriber alters a header after another subscriber has received the same message, processing outcomes could depend on execution order and read timing.

Note: a non-modifiable headers map does not mean every object stored inside it is deeply immutable. If a header contains a mutable object, code can still mutate the internal state of that object. Therefore, prefer simple metadata types and immutable values such as String, UUID, numbers, enums, or immutable time types.

### 2.2 MessageHeaderAccessor: Tool for Manipulating Metadata

`MessageHeaderAccessor` belongs to the `org.springframework.messaging.support` package. It provides methods to:

- Read a header by name.
- Set a new header or replace an existing value.
- Set only when a header does not yet exist.
- Remove a header.
- Copy headers from another map.
- Obtain a `MessageHeaders` instance to construct a message.
- Obtain a mutable accessor from an existing message.

Some commonly used methods:

| API | Usage |
|---|---|
| `getHeader(name)` | Reads a header value |
| `setHeader(name, value)` | Adds or replaces a header value |
| `setHeaderIfAbsent(name, value)` | Sets only when no value exists yet |
| `removeHeader(name)` | Removes a header |
| `copyHeaders(map)` | Copies headers; values with matching names may be overwritten |
| `copyHeadersIfAbsent(map)` | Copies only headers that are not yet present |
| `getMessageHeaders()` | Retrieves MessageHeaders to construct a message |
| `getMutableAccessor(message)` | Obtains a mutable accessor initialized from a message |

Use an accessor during the message creation or transformation phase. Once the new message is built, pass that message to the next channel or handler and treat the metadata as finalized.

## 3. Creating a Message with an Accessor

You can instantiate a new accessor, set custom headers, and create a message using `MessageBuilder.createMessage`.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class HeaderAccessorDemo {

    public static void main(String[] args) {
        MessageHeaderAccessor accessor = new MessageHeaderAccessor();
        accessor.setHeader("app.correlationId", "corr-42");
        accessor.setHeader("app.source", "checkout");

        Message<String> message = MessageBuilder.createMessage(
                "order.created",
                accessor.getMessageHeaders()
        );

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("app.correlationId"));
    }
}
~~~

Output:

~~~text
order.created
corr-42
~~~

In this example:

1. Create a standalone accessor.
2. Add the correlation ID and message source.
3. Retrieve MessageHeaders from the accessor.
4. Use the payload and headers to construct a complete message.
5. Read metadata via `message.getHeaders()`.

The example uses Spring Framework's `spring-messaging` package. In a Spring Boot project, let the dependency management of your Boot version manage the compatible Spring version.

## 4. Obtaining a Mutable Accessor from an Existing Message

A common scenario is that a message has already been created, yet needs additional metadata before being sent to the next step. Do not modify `message.getHeaders()` directly. Obtain a mutable accessor and create a new message.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class EnrichMessageDemo {

    public static void main(String[] args) {
        Message<String> original = MessageBuilder
                .withPayload("order.created")
                .setHeader("app.correlationId", "corr-42")
                .build();

        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(original);

        accessor.setHeader("app.processingAttempt", 1);

        Message<String> enriched = MessageBuilder.createMessage(
                original.getPayload(),
                accessor.getMessageHeaders()
        );

        System.out.println(enriched.getPayload());
        System.out.println(enriched.getHeaders().get("app.correlationId"));
        System.out.println(enriched.getHeaders().get("app.processingAttempt"));
    }
}
~~~

Output:

~~~text
order.created
corr-42
1
~~~

`getMutableAccessor(message)` creates or provides an editable accessor based on the headers of the passed-in message. The accessor preserves existing metadata so you can deliberately add or update entries.

In the example, the new message keeps the original payload and correlation ID while adding the processing attempt. The original message remains the input object of the transformation step. Forward the new message to the next channel.

This pattern illustrates a clear principle: **transform a message by creating the next message with prepared metadata**, rather than letting multiple components mutate a message that is currently in flight.

## 5. Choosing the Right Way to Update Headers

### 5.1 Overwrite vs. Set Only If Missing

Two operations have different semantics:

~~~java
accessor.setHeader("app.correlationId", "corr-new");
accessor.setHeaderIfAbsent("app.source", "fallback");
~~~

- `setHeader` replaces the current value if the header name already exists.
- `setHeaderIfAbsent` preserves the existing value and only adds a value when the header has not been set.

This matters when a message traverses multiple layers. For example, if a gateway has already generated a correlation ID, a downstream handler should not overwrite it with a different ID. In that case, `setHeaderIfAbsent` is more appropriate.

If the application intentionally creates a new message and needs to reset metadata according to a contract, `setHeader` may be the right choice.

### 5.2 Removing and Copying Headers

Use `removeHeader` when metadata is no longer valid in the next step:

~~~java
accessor.removeHeader("app.internalToken");
~~~

Use `copyHeaders` when you need to copy a group of metadata and accept overwriting duplicate names:

~~~java
accessor.copyHeaders(sourceHeaders);
~~~

Use `copyHeadersIfAbsent` when you want to preserve values set earlier:

~~~java
accessor.copyHeadersIfAbsent(defaultHeaders);
~~~

Do not copy all headers mechanically across every boundary. A message may contain internal headers, protocol headers, security details, or data meaningful only within a specific session. Define the list of metadata that actually needs to be propagated.

### 5.3 System Headers and Custom Headers

Spring manages several foundational headers such as ID and timestamp. Do not arbitrarily overwrite system headers or use framework names for application business data.

Establish a naming convention for application metadata, for example:

- `app.correlationId`: links messages within the same business flow.
- `app.tenantId`: tenant context after verification.
- `app.source`: component that created the message.
- `app.processingAttempt`: processing attempt count per application convention.
- `app.schemaVersion`: payload schema version if required by the contract.

Namespaced names prevent collisions with headers managed by Spring or protocol adapters. Each header's data type and meaning should be defined consistently in the application contract.

## 6. Protocol-Specific Accessors

`MessageHeaderAccessor` is the foundational class. Several Spring modules provide specialized accessors for working with metadata structured specifically for a protocol or message type.

Examples in Spring messaging:

- `SimpMessageHeaderAccessor` provides access to headers related to the simple messaging model, such as destination, session, and message type.
- `StompHeaderAccessor` provides ways to work with STOMP headers and commands.
- `NativeMessageHeaderAccessor` supports the native headers group coming from protocols or adapters.

When handling messages of a specific protocol, use the corresponding accessor to read and update metadata according to that protocol's semantics. Do not guess header names or manually alter the native header structure via the generic map when the framework already provides a specialized API.

You can retrieve a specialized accessor attached to a message with an API like:

~~~java
SimpMessageHeaderAccessor accessor =
        MessageHeaderAccessor.getAccessor(
                message,
                SimpMessageHeaderAccessor.class
        );
~~~

The return value may be `null` if the message is not associated with an accessor of the requested type. Therefore, only use this API when the processing flow guarantees the message comes from the matching infrastructure, or check the result before accessing it.

Specialized accessors do not turn every message into a STOMP or WebSocket message. Use them only within the proper integration context.

## 7. Mutable State and Message Lifecycle

### 7.1 Why Finalize Metadata Before Sending

A message can traverse multiple channels, interceptors, and handlers. A channel can also distribute the same message to multiple subscribers. If headers remain mutable when components begin processing in parallel, one component may observe a different value than another.

For example, two subscribers receive the same message. The first subscriber modifies the correlation ID in a shared map; the second subscriber might log or call a service with the altered correlation ID. Tracing results then become unreliable.

Therefore, complete all metadata updates before publishing the message. After sending, treat the message and its header values as read-only data.

### 7.2 setLeaveMutable and Advanced Cases

`MessageHeaderAccessor` has a `setLeaveMutable(boolean)` API to control keeping the MessageHeaders created from the accessor in a mutable state. This is an advanced option, typically needed only in deliberate framework or interceptor flows that must continue completing headers before the message is finalized.

Do not enable this mode out of habit. If a message with mutable headers is shared or handed off to asynchronous processing before completion, components can mutate the same state. Use it only when you have clearly defined who may update, at which stage updates occur, and when the state becomes immutable.

For ordinary business code, using a mutable accessor within a short scope, creating a finalized message, and sending it is simpler and safer.

### 7.3 Payload Can Also Contain Mutable State

Immutable headers do not automatically make the payload immutable. For example, a payload that is an `ArrayList` or a DTO with setters can still be mutated after the message is sent.

If multiple handlers read the payload, prefer:

- Java records or immutable DTOs.
- Unmodifiable collections or defensive copies.
- Not sharing mutable objects across threads without proper synchronization.
- Creating a new payload when data needs to be transformed.

This rule applies to both payloads and objects stored inside custom headers.

## 8. Using an Accessor in ChannelInterceptor

An interceptor is a suitable place to attach shared technical metadata to a sending flow, such as acceptance time or trace codes. However, interceptors should avoid holding business rules for individual message types.

Illustrative example of pre-send processing:

~~~java
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class ProcessingMetadataInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(message);

        accessor.setHeader("app.acceptedAt", Instant.now());

        return MessageBuilder.createMessage(
                message.getPayload(),
                accessor.getMessageHeaders()
        );
    }
}
~~~

The interceptor obtains a mutable accessor from the message, adds an application-level timestamp, and returns a new message. This timestamp represents when the interceptor accepted the message according to the current process's clock; it is not necessarily when the message was created in the source system.

Register the interceptor with the corresponding channel using the application's configuration mechanism. Do not attach an interceptor globally if the metadata is only meaningful for a specific flow.

If processing duration needs to be measured, consider using dedicated tracing or metrics. Do not turn headers into a dumping ground for arbitrary operational numbers or logs.

## 9. Security and Trustworthiness of Metadata

Headers are data accompanying a message, not proof that the values inside them are trustworthy.

For example, a client can send a self-declared `app.tenantId` or `userRole` header. The server should not use those values to decide access permissions unless they have been verified by a trusted authentication and authorization mechanism.

Principles to uphold:

- Authenticate the sender before trusting identity-related metadata.
- Do not use client-supplied headers to grant permissions or select a tenant without verification.
- Forward only necessary headers; strip tokens or sensitive metadata before sending to external systems.
- Do not log all headers by default because they may contain personal data or secrets.
- Limit the count, size, and data types of custom headers.
- Use correlation ID for tracing, not as authentication credentials.

When a message crosses a broker or protocol adapter, identify which headers are mapped, which are renamed, and which are not preserved. Do not assume all internal Spring metadata will automatically appear intact on the receiving side.

## 10. Testing Header Creation and Transformation

Three categories of behavior should be tested:

1. **Message creation:** payload and custom headers have the expected values.
2. **Message transformation:** a mutable accessor preserves required metadata, adds or replaces the right headers, and does not unexpectedly alter the payload.
3. **State protection:** code reads headers after building the message without relying on direct map mutation.

Unit test example with JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

class MessageHeaderAccessorTest {

    @Test
    void shouldEnrichMessageWithoutChangingOriginalPayload() {
        Message<String> original = MessageBuilder
                .withPayload("order.created")
                .setHeader("app.correlationId", "corr-42")
                .build();

        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(original);
        accessor.setHeader("app.processingAttempt", 2);

        Message<String> enriched = MessageBuilder.createMessage(
                original.getPayload(),
                accessor.getMessageHeaders()
        );

        assertEquals("order.created", enriched.getPayload());
        assertEquals("corr-42",
                enriched.getHeaders().get("app.correlationId"));
        assertEquals(2,
                enriched.getHeaders().get("app.processingAttempt"));
        assertEquals(null,
                original.getHeaders().get("app.processingAttempt"));
    }

    @Test
    void messageHeadersShouldNotBeModifiedDirectly() {
        Message<String> message = MessageBuilder
                .withPayload("order.created")
                .build();

        assertThrows(UnsupportedOperationException.class,
                () -> message.getHeaders().put("app.source", "checkout"));
    }
}
~~~

These tests verify message creation and transformation behavior. If the project uses specialized accessors or interceptors, add tests for those specific protocols and channels. Unit tests do not replace integration tests with a broker when verifying header translation across network boundaries.

## 11. Common Pitfalls

- **Calling put directly on MessageHeaders:** message headers are designed for reading; direct map updates are typically rejected.
- **Assuming MessageHeaderAccessor makes the payload immutable:** the accessor only manages headers; the payload object can still be mutable.
- **Modifying headers after publishing:** creates race conditions when a message is shared across multiple subscribers or threads.
- **Enabling leaveMutable without reason:** exposes shared state to components that should not modify metadata.
- **Overwriting correlation ID in a downstream layer:** breaks the link between messages belonging to the same business flow.
- **Copying all headers:** can leak tokens, session metadata, or internal headers to other systems.
- **Confusing custom headers with authentication headers:** client-sent values must be verified before being used in security decisions.
- **Using the wrong protocol accessor:** STOMP or Simp accessors are only appropriate when the message belongs to the matching integration context.
- **Failing to define namespaces and data types:** modules easily reuse names or interpret the same header differently.
- **Using headers to hold large mutable objects:** increases state-sharing risks, memory overhead, and serialization issues.

## 12. Checklist When Working with MessageHeaderAccessor

Before forwarding a message to the next channel or handler, verify:

- Have payload and metadata been clearly separated?
- Can headers be read through MessageHeaders without direct modification?
- When changes are needed, are MessageHeaderAccessor or MessageBuilder used?
- Are correlation IDs and valid metadata from the original message preserved?
- Are headers set by upstream layers protected from accidental overwriting?
- Are internal or sensitive headers stripped before crossing boundaries?
- Are specialized accessors used when working with STOMP or simple messaging?
- Are headers finalized before publishing or parallel processing?
- Do payloads and objects in headers avoid sharing mutable state?
- Have unit tests verified both enrichment and protection against direct header mutation?

By understanding the lifecycle of accessors and messages, you can enrich metadata in a controlled manner, maintain consistency across handlers, and avoid hard-to-reproduce bugs caused by mutable state in messaging systems.